from pathlib import Path

ROOT = Path(__file__).resolve().parent

def write_file(relative_path: str, content: str):
    path = ROOT / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.strip() + "\n", encoding="utf-8")
    print(f"updated: {relative_path}")

write_file("backend/app/rag_engine.py", r"""
import csv
import math
from pathlib import Path
from typing import Dict, List


DATA_DIR = Path(__file__).resolve().parents[2] / "data"
PAST_CASES_PATH = DATA_DIR / "past_cases.csv"
POLICY_PATH = DATA_DIR / "knowledge_base" / "support_policy.txt"


def _tokenize(text: str) -> set:
    clean = ""
    for char in str(text).lower():
        clean += char if char.isalnum() else " "
    return {token for token in clean.split() if len(token) > 2}


def _similarity(a: str, b: str) -> float:
    a_tokens = _tokenize(a)
    b_tokens = _tokenize(b)

    if not a_tokens or not b_tokens:
        return 0.0

    overlap = len(a_tokens.intersection(b_tokens))
    denominator = math.sqrt(len(a_tokens) * len(b_tokens))
    return round(overlap / denominator, 4)


def _read_csv(path: Path) -> List[Dict]:
    if not path.exists():
        return []

    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def _read_policy() -> str:
    if not POLICY_PATH.exists():
        return ""

    return POLICY_PATH.read_text(encoding="utf-8")


def retrieve_similar_cases(task: Dict, top_k: int = 5) -> List[Dict]:
    cases = _read_csv(PAST_CASES_PATH)
    query = " ".join([
        str(task.get("title", "")),
        str(task.get("description", "")),
        str(task.get("category", "")),
        " ".join(task.get("required_skills", []) or []),
    ])

    scored = []
    for case in cases:
        case_text = " ".join([
            case.get("title", ""),
            case.get("description", ""),
            case.get("category", ""),
            case.get("skills", ""),
            case.get("resolution_notes", ""),
        ])

        score = _similarity(query, case_text)

        if str(task.get("category", "")).lower() == str(case.get("category", "")).lower():
            score += 0.15

        scored.append({
            **case,
            "similarity_score": round(min(score, 1.0), 4),
        })

    scored.sort(key=lambda item: item["similarity_score"], reverse=True)
    return [item for item in scored[:top_k] if item["similarity_score"] > 0]


def retrieve_policy_context(task: Dict) -> List[str]:
    policy_text = _read_policy()
    if not policy_text:
        return []

    chunks = [
        chunk.strip()
        for chunk in policy_text.split("\n\n")
        if chunk.strip()
    ]

    query = " ".join([
        str(task.get("title", "")),
        str(task.get("description", "")),
        str(task.get("category", "")),
        str(task.get("priority", "")),
    ])

    scored_chunks = [
        {
            "text": chunk,
            "score": _similarity(query, chunk),
        }
        for chunk in chunks
    ]

    scored_chunks.sort(key=lambda item: item["score"], reverse=True)
    return [item["text"] for item in scored_chunks[:3] if item["score"] > 0]


def build_rag_context(task: Dict) -> Dict:
    similar_cases = retrieve_similar_cases(task)
    policy_context = retrieve_policy_context(task)

    resource_case_stats = {}

    for case in similar_cases:
        resource_name = case.get("resource_name", "")
        if not resource_name:
            continue

        stats = resource_case_stats.setdefault(resource_name, {
            "similar_cases": 0,
            "successful_cases": 0,
            "escalations": 0,
            "avg_resolution_minutes": [],
            "similarity_total": 0.0,
        })

        stats["similar_cases"] += 1
        stats["similarity_total"] += float(case.get("similarity_score") or 0)

        if str(case.get("success", "")).lower() == "true":
            stats["successful_cases"] += 1

        if str(case.get("escalated", "")).lower() == "true":
            stats["escalations"] += 1

        try:
            stats["avg_resolution_minutes"].append(float(case.get("completed_minutes") or 0))
        except ValueError:
            pass

    for stats in resource_case_stats.values():
        values = stats["avg_resolution_minutes"]
        stats["avg_resolution_minutes"] = round(sum(values) / len(values), 2) if values else None
        stats["avg_similarity"] = round(
            stats["similarity_total"] / max(stats["similar_cases"], 1),
            4,
        )

    return {
        "similar_cases": similar_cases,
        "policy_context": policy_context,
        "resource_case_stats": resource_case_stats,
    }
""")

write_file("backend/app/agentic_assignment_engine.py", r"""
from typing import Dict, Optional

from .database import load_resources
from .explanation_engine import explain_unassigned
from .rag_engine import build_rag_context
from .scoring_engine import score_resource_for_task
from .task_parser import parse_task


def _case_bonus_for_resource(resource: Dict, rag_context: Dict) -> Dict:
    name = resource.get("name", "")
    stats = rag_context.get("resource_case_stats", {}).get(name)

    if not stats:
        return {
            "bonus": 0.0,
            "reason": "no strong similar-case history found",
        }

    successful = stats.get("successful_cases", 0)
    similar = max(stats.get("similar_cases", 1), 1)
    escalations = stats.get("escalations", 0)
    avg_similarity = float(stats.get("avg_similarity") or 0)

    success_ratio = successful / similar
    escalation_penalty = escalations * 2.0

    bonus = (success_ratio * 8.0) + (avg_similarity * 6.0) - escalation_penalty
    bonus = max(-5.0, min(12.0, bonus))

    return {
        "bonus": round(bonus, 2),
        "reason": (
            f"RAG found {similar} similar past case(s), "
            f"{successful} successful, {escalations} escalated"
        ),
    }


def _explain_agentic_assignment(task: Dict, winner: Dict, rag_context: Dict, candidates: list) -> str:
    similar_cases = rag_context.get("similar_cases", [])
    policy_context = rag_context.get("policy_context", [])

    base = (
        f"Agentic RAG assigned this task to {winner.get('resource_name')} because "
        f"the agent passed shift, availability, workload, and skill checks, then received "
        f"the best combined score after similar-case retrieval. "
    )

    if winner.get("positive_reasons"):
        base += "Core reasons: " + "; ".join(winner["positive_reasons"][:4]) + ". "

    if winner.get("rag_reason"):
        base += "RAG evidence: " + winner["rag_reason"] + ". "

    if similar_cases:
        top_case = similar_cases[0]
        base += (
            f"Most similar past case: '{top_case.get('title')}' handled by "
            f"{top_case.get('resource_name')} with similarity {top_case.get('similarity_score')}. "
        )

    if policy_context:
        base += "Relevant policy/SOP context was also retrieved before scoring. "

    skipped = [
        candidate for candidate in candidates
        if not candidate.get("eligible") and candidate.get("rejection_reasons")
    ][:2]

    for item in skipped:
        base += (
            f"{item.get('resource_name')} was skipped because "
            f"{', '.join(item.get('rejection_reasons', [])[:2])}. "
        )

    return base.strip()


def assign_task_agentic(task: Dict, now_hhmm: Optional[str] = None) -> Dict:
    resources = load_resources()
    parsed_task = parse_task(task)
    rag_context = build_rag_context(parsed_task)

    candidates = []

    for resource in resources:
        candidate = score_resource_for_task(parsed_task, resource, now_hhmm=now_hhmm)
        rag_boost = _case_bonus_for_resource(resource, rag_context)

        candidate["base_score"] = candidate["final_score"]
        candidate["rag_bonus"] = rag_boost["bonus"]
        candidate["rag_reason"] = rag_boost["reason"]

        if candidate["eligible"]:
            candidate["final_score"] = round(candidate["final_score"] + rag_boost["bonus"], 2)
            candidate["breakdown"]["rag_similar_case_bonus"] = rag_boost["bonus"]
            if rag_boost["bonus"] > 0:
                candidate["positive_reasons"].append(rag_boost["reason"])

        candidates.append(candidate)

    candidates.sort(key=lambda item: item["final_score"], reverse=True)
    valid_candidates = [candidate for candidate in candidates if candidate["eligible"]]

    if not valid_candidates:
        return {
            "task": parsed_task,
            "assigned": False,
            "assigned_resource": None,
            "mode": "agentic_rag",
            "explanation": explain_unassigned(parsed_task, candidates),
            "rag_context": rag_context,
            "candidates": candidates,
        }

    winner = valid_candidates[0]

    return {
        "task": parsed_task,
        "assigned": True,
        "assigned_resource": {
            "resource_id": winner["resource_id"],
            "name": winner["resource_name"],
            "score": winner["final_score"],
            "base_score": winner["base_score"],
            "rag_bonus": winner["rag_bonus"],
        },
        "mode": "agentic_rag",
        "explanation": _explain_agentic_assignment(parsed_task, winner, rag_context, candidates),
        "rag_context": rag_context,
        "candidates": candidates,
    }
""")

write_file("backend/app/main.py", r"""
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .agentic_assignment_engine import assign_task_agentic
from .assignment_engine import assign_single_task, assign_tasks
from .database import load_history, load_resources, load_tasks, save_resources
from .schemas import AssignmentRequest, ResourceIn, TaskIn


app = FastAPI(
    title="AI Task Allocation System",
    description="Smart workforce task allocation using availability, shift timing, workload, skills, past performance, and Agentic RAG.",
    version="1.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _next_resource_id(resources):
    used_numbers = []
    for resource in resources:
        rid = str(resource.get("resource_id", "")).upper().replace("R", "")
        if rid.isdigit():
            used_numbers.append(int(rid))
    return f"R{max(used_numbers, default=0) + 1}"


@app.get("/")
def health_check():
    return {
        "status": "ok",
        "app": "AI Task Allocation System",
        "message": "Backend is running. Open /docs for API testing.",
    }


@app.get("/resources")
def get_resources():
    return load_resources()


@app.post("/resources")
def create_resource(resource: ResourceIn):
    resources = load_resources()
    data = resource.model_dump()

    if not data["resource_id"]:
        data["resource_id"] = _next_resource_id(resources)

    if any(item["resource_id"] == data["resource_id"] for item in resources):
        raise HTTPException(status_code=409, detail="Resource ID already exists.")

    data["skills"] = [skill.strip().lower() for skill in data["skills"] if skill.strip()]
    data["handled_categories"] = [
        category.strip().lower()
        for category in data["handled_categories"]
        if category.strip()
    ]
    data["status"] = data["status"].lower()

    resources.append(data)
    save_resources(resources)

    return {
        "message": "Resource created successfully.",
        "resource": data,
    }


@app.put("/resources/{resource_id}")
def update_resource(resource_id: str, resource: ResourceIn):
    resources = load_resources()
    data = resource.model_dump()
    data["resource_id"] = resource_id
    data["skills"] = [skill.strip().lower() for skill in data["skills"] if skill.strip()]
    data["handled_categories"] = [
        category.strip().lower()
        for category in data["handled_categories"]
        if category.strip()
    ]
    data["status"] = data["status"].lower()

    for index, existing in enumerate(resources):
        if existing["resource_id"] == resource_id:
            resources[index] = data
            save_resources(resources)
            return {
                "message": "Resource updated successfully.",
                "resource": data,
            }

    raise HTTPException(status_code=404, detail="Resource not found.")


@app.delete("/resources/{resource_id}")
def delete_resource(resource_id: str):
    resources = load_resources()
    remaining = [resource for resource in resources if resource["resource_id"] != resource_id]

    if len(remaining) == len(resources):
        raise HTTPException(status_code=404, detail="Resource not found.")

    save_resources(remaining)

    return {
        "message": "Resource deleted successfully.",
        "resource_id": resource_id,
    }


@app.get("/tasks")
def get_tasks():
    return load_tasks()


@app.get("/history")
def get_history():
    return load_history()


@app.post("/assign")
def assign_task(task: TaskIn, now_hhmm: Optional[str] = Query(default=None)):
    return assign_single_task(task.model_dump(), now_hhmm=now_hhmm)


@app.post("/assign/agentic")
def assign_task_with_agentic_rag(task: TaskIn, now_hhmm: Optional[str] = Query(default=None)):
    return assign_task_agentic(task.model_dump(), now_hhmm=now_hhmm)


@app.post("/assign/batch")
def assign_batch(payload: AssignmentRequest):
    return assign_tasks(
        [task.model_dump() for task in payload.tasks],
        now_hhmm=payload.now_hhmm,
    )


@app.post("/assign/sample")
def assign_sample(now_hhmm: Optional[str] = Query(default="10:30")):
    return assign_tasks(load_tasks(), now_hhmm=now_hhmm)
""")

write_file("data/past_cases.csv", r"""
case_id,title,description,category,skills,resource_name,completed_minutes,success,customer_rating,escalated,resolution_notes
C1,Customer payment failed after card checkout,Payment failed after checkout but amount was debited,payment,"payments;billing;customer_support",Amit,32,true,5,false,Checked gateway logs verified transaction and guided refund flow
C2,UPI payment stuck during checkout,UPI payment showed pending and customer could not complete order,payment,"payments;billing;customer_support",Sara,28,true,5,false,Matched gateway reference and resolved with payment retry instructions
C3,Refund for duplicate charge,Customer was charged twice and requested urgent refund,billing,"billing;refunds;customer_support",Amit,36,true,5,false,Validated duplicate charge and initiated refund under billing SOP
C4,API timeout during partner integration,Partner API response was slow and timing out,technical,"technical_support;api;debugging",Rohit,42,true,5,false,Debugged API latency and escalated infra metrics check
C5,Login locked account,User could not login because account was locked,account,"account_management;customer_support",Neha,48,true,4,false,Verified identity and reset account lock state
C6,Payment failure assigned to technical queue,Payment issue was assigned to technical resource without billing context,payment,"payments;billing;customer_support",Rohit,95,false,2,true,Escalated because billing/payment process knowledge was missing
C7,Refund policy confusion,Customer asked for refund after failed service renewal,billing,"billing;refunds;customer_support",Priya,41,true,5,false,Followed refund policy and explained SLA to customer
C8,General dashboard usage question,Customer asked how to use analytics dashboard,general,"customer_support",Joe,25,true,4,false,Shared dashboard guide and resolved without escalation
""")

write_file("data/knowledge_base/support_policy.txt", r"""
Payment Failure SOP
For payment failure, checkout failure, UPI pending, card failure, or amount debited cases, prefer agents with payment and billing experience. High priority payment tasks should be handled by agents with previous successful payment cases and low current workload.

Refund SOP
For refund or duplicate charge cases, prefer billing/refund specialists. If the customer says charged twice, duplicate debit, failed payment with deduction, or urgent refund, the system should consider refund experience and customer support skill.

Technical Incident SOP
For API latency, server error, timeout, production bug, or integration failure, prefer technical support agents with API/debugging skills. Urgent technical issues should not be assigned to agents without technical debugging experience.

Account Support SOP
For login, password, locked account, signup, or profile access problems, prefer account management and customer support agents.

Workload Policy
Never assign a task to a resource that is offline, outside shift timing, or already at maximum workload. Prefer idle resources when skill match and past performance are acceptable.

Escalation Policy
If similar past cases show escalation for a resource, reduce confidence for that resource on similar future tasks. Successful similar cases should increase confidence.
""")

write_file("frontend/src/components/TaskForm.jsx", r"""
import { useState } from "react";

const DEFAULT_TASK = {
  title: "Customer payment failed",
  description: "Customer says payment failed after checkout using card",
  priority: "high",
  category: "payment",
  required_skills: "payments,billing,customer_support",
  sla_minutes: 60,
};

export default function TaskForm({ onAssign, onAgenticAssign, loading, agenticLoading }) {
  const [task, setTask] = useState(DEFAULT_TASK);

  function updateField(field, value) {
    setTask((current) => ({
      ...current,
      [field]: value,
    }));
  }

  function buildPayload() {
    return {
      task_id: `CUSTOM-${Date.now()}`,
      title: task.title.trim(),
      description: task.description.trim(),
      priority: task.priority,
      category: task.category.trim() || null,
      required_skills: task.required_skills
        .split(",")
        .map((skill) => skill.trim().toLowerCase())
        .filter(Boolean),
      sla_minutes: Number(task.sla_minutes) || 120,
    };
  }

  function submitTask(event) {
    event.preventDefault();
    onAssign(buildPayload());
  }

  function submitAgenticTask() {
    onAgenticAssign(buildPayload());
  }

  return (
    <div className="card">
      <h2>Assign a Custom Task</h2>
      <p className="muted">
        Enter a real support/service task. Normal assignment uses the scoring engine.
        Agentic RAG also retrieves similar past cases and SOP/policy context before scoring.
      </p>

      <form className="taskForm" onSubmit={submitTask}>
        <label>
          Task title
          <input
            value={task.title}
            onChange={(event) => updateField("title", event.target.value)}
            placeholder="Example: Customer payment failed"
            required
          />
        </label>

        <label>
          Description
          <textarea
            value={task.description}
            onChange={(event) => updateField("description", event.target.value)}
            placeholder="Describe what happened..."
            rows={4}
          />
        </label>

        <div className="formGrid">
          <label>
            Priority
            <select
              value={task.priority}
              onChange={(event) => updateField("priority", event.target.value)}
            >
              <option value="urgent">urgent</option>
              <option value="high">high</option>
              <option value="medium">medium</option>
              <option value="low">low</option>
            </select>
          </label>

          <label>
            Category
            <input
              value={task.category}
              onChange={(event) => updateField("category", event.target.value)}
              placeholder="payment, technical, billing..."
            />
          </label>

          <label>
            SLA minutes
            <input
              type="number"
              value={task.sla_minutes}
              onChange={(event) => updateField("sla_minutes", event.target.value)}
              min="1"
            />
          </label>
        </div>

        <label>
          Required skills
          <input
            value={task.required_skills}
            onChange={(event) => updateField("required_skills", event.target.value)}
            placeholder="payments,billing,customer_support"
          />
          <small>Use comma-separated skills.</small>
        </label>

        <div className="buttonRow">
          <button type="submit" disabled={loading || agenticLoading}>
            {loading ? "Finding Best Agent..." : "Normal Assignment"}
          </button>

          <button
            type="button"
            className="secondaryButton"
            disabled={loading || agenticLoading}
            onClick={submitAgenticTask}
          >
            {agenticLoading ? "Running Agentic RAG..." : "Agentic RAG Assignment"}
          </button>
        </div>
      </form>
    </div>
  );
}
""")

write_file("frontend/src/components/AssignmentCard.jsx", r"""
function RagContext({ context }) {
  if (!context) return null;

  const similarCases = context.similar_cases || [];
  const policies = context.policy_context || [];

  return (
    <div className="ragBox">
      <h4>Agentic RAG Evidence</h4>

      {similarCases.length > 0 && (
        <>
          <strong>Similar past cases</strong>
          <div className="ragCases">
            {similarCases.slice(0, 3).map((item) => (
              <div className="ragCase" key={item.case_id}>
                <b>{item.title}</b>
                <span>
                  Agent: {item.resource_name} • Similarity: {item.similarity_score} •
                  Success: {item.success} • Escalated: {item.escalated}
                </span>
              </div>
            ))}
          </div>
        </>
      )}

      {policies.length > 0 && (
        <>
          <strong>Retrieved SOP / policy context</strong>
          <ul>
            {policies.slice(0, 2).map((policy, index) => (
              <li key={index}>{policy}</li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}

export default function AssignmentCard({ item }) {
  const topCandidates = item.candidates?.slice(0, 3) || [];

  return (
    <div className="assignmentCard">
      <div className="assignmentHeader">
        <div>
          <h3>{item.task.title}</h3>
          <p>
            {item.task.category} • {item.task.priority}
            {item.mode === "agentic_rag" ? " • Agentic RAG mode" : ""}
          </p>
        </div>

        {item.assigned ? (
          <div className="assignedBox">
            <span>Assigned to</span>
            <strong>{item.assigned_resource.name}</strong>
            <small>Score {item.assigned_resource.score}</small>
            {item.assigned_resource.rag_bonus !== undefined && (
              <small>
                Base {item.assigned_resource.base_score} + RAG {item.assigned_resource.rag_bonus}
              </small>
            )}
          </div>
        ) : (
          <div className="unassignedBox">Unassigned</div>
        )}
      </div>

      <p className="explanation">{item.explanation}</p>

      <div className="candidateGrid">
        {topCandidates.map((candidate) => (
          <div className="candidate" key={candidate.resource_id}>
            <strong>{candidate.resource_name}</strong>
            <span>{candidate.eligible ? "Eligible" : "Skipped"}</span>
            <b>{candidate.final_score}</b>
            {candidate.rag_bonus !== undefined && (
              <small>Base: {candidate.base_score} | RAG: {candidate.rag_bonus}</small>
            )}
            <small>
              {candidate.eligible
                ? candidate.positive_reasons?.slice(0, 2).join(", ")
                : candidate.rejection_reasons?.slice(0, 2).join(", ")}
            </small>
          </div>
        ))}
      </div>

      <RagContext context={item.rag_context} />
    </div>
  );
}
""")

write_file("frontend/src/App.jsx", r"""
import { useEffect, useState } from "react";

import { apiDelete, apiGet, apiPost } from "./api/client";
import AssignmentCard from "./components/AssignmentCard";
import ResourceForm from "./components/ResourceForm";
import ResourceTable from "./components/ResourceTable";
import TaskForm from "./components/TaskForm";
import TaskTable from "./components/TaskTable";

function SingleAssignmentResult({ result }) {
  if (!result) return null;

  return (
    <div className="card">
      <h2>
        {result.mode === "agentic_rag"
          ? "Agentic RAG Assignment Result"
          : "Custom Task Assignment Result"}
      </h2>
      <AssignmentCard item={result} />
    </div>
  );
}

function BatchAssignmentResult({ result }) {
  if (!result) return null;

  return (
    <div className="card">
      <h2>Sample Batch Assignment Result</h2>
      <p>
        Assigned {result.assigned_count} of {result.total_tasks} tasks.
        Unassigned: {result.unassigned_count}.
      </p>

      <div className="results">
        {result.assignments.map((item) => (
          <AssignmentCard key={item.task.task_id} item={item} />
        ))}
      </div>
    </div>
  );
}

export default function App() {
  const [resources, setResources] = useState([]);
  const [tasks, setTasks] = useState([]);
  const [batchResult, setBatchResult] = useState(null);
  const [singleResult, setSingleResult] = useState(null);
  const [now, setNow] = useState("10:30");
  const [loadingBatch, setLoadingBatch] = useState(false);
  const [loadingSingle, setLoadingSingle] = useState(false);
  const [loadingAgentic, setLoadingAgentic] = useState(false);
  const [loadingResource, setLoadingResource] = useState(false);
  const [error, setError] = useState("");

  async function loadData() {
    try {
      const [resourceData, taskData] = await Promise.all([
        apiGet("/resources"),
        apiGet("/tasks"),
      ]);

      setResources(resourceData);
      setTasks(taskData);
    } catch (err) {
      setError(err.message);
    }
  }

  async function createResource(payload) {
    setLoadingResource(true);
    setError("");

    try {
      await apiPost("/resources", payload);
      await loadData();
    } catch (err) {
      setError(err.message);
    } finally {
      setLoadingResource(false);
    }
  }

  async function deleteResource(resourceId) {
    const confirmed = window.confirm("Delete this resource?");
    if (!confirmed) return;

    setError("");

    try {
      await apiDelete(`/resources/${resourceId}`);
      await loadData();
    } catch (err) {
      setError(err.message);
    }
  }

  async function runSampleAssignment() {
    setLoadingBatch(true);
    setError("");

    try {
      const data = await apiPost(`/assign/sample?now_hhmm=${encodeURIComponent(now)}`);
      setBatchResult(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoadingBatch(false);
    }
  }

  async function runCustomAssignment(taskPayload) {
    setLoadingSingle(true);
    setError("");

    try {
      const data = await apiPost(`/assign?now_hhmm=${encodeURIComponent(now)}`, taskPayload);
      setSingleResult(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoadingSingle(false);
    }
  }

  async function runAgenticAssignment(taskPayload) {
    setLoadingAgentic(true);
    setError("");

    try {
      const data = await apiPost(`/assign/agentic?now_hhmm=${encodeURIComponent(now)}`, taskPayload);
      setSingleResult(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoadingAgentic(false);
    }
  }

  useEffect(() => {
    loadData();
  }, []);

  return (
    <main className="app">
      <section className="hero">
        <div>
          <h1>AI Task Allocation System</h1>
          <p>
            Assign service/support tasks using deterministic scoring, idle checks,
            workload constraints, and Agentic RAG retrieval from past cases and SOPs.
          </p>
        </div>

        <div className="controls">
          <label>
            Demo time{" "}
            <input value={now} onChange={(event) => setNow(event.target.value)} />
          </label>
          <button onClick={runSampleAssignment} disabled={loadingBatch}>
            {loadingBatch ? "Assigning..." : "Run Sample Batch"}
          </button>
        </div>
      </section>

      {error && <div className="error">{error}</div>}

      <section className="grid">
        <TaskForm
          onAssign={runCustomAssignment}
          onAgenticAssign={runAgenticAssignment}
          loading={loadingSingle}
          agenticLoading={loadingAgentic}
        />

        <SingleAssignmentResult result={singleResult} />

        <ResourceForm onCreate={createResource} loading={loadingResource} />
        <ResourceTable resources={resources} onDelete={deleteResource} />

        <TaskTable tasks={tasks} />

        <BatchAssignmentResult result={batchResult} />
      </section>
    </main>
  );
}
""")

css_path = ROOT / "frontend/src/styles.css"
extra_css = r"""

.buttonRow {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.secondaryButton {
  background: #8b5cf6;
  color: #ffffff;
}

.ragBox {
  margin-top: 16px;
  border: 1px solid #334155;
  border-radius: 14px;
  padding: 14px;
  background: #0b1222;
}

.ragBox h4 {
  margin: 0 0 12px;
  color: #c4b5fd;
}

.ragBox strong {
  display: block;
  margin: 12px 0 8px;
  color: #dbeafe;
}

.ragCases {
  display: grid;
  gap: 8px;
}

.ragCase {
  padding: 10px;
  border-radius: 12px;
  background: #111827;
  border: 1px solid #263244;
}

.ragCase b,
.ragCase span {
  display: block;
}

.ragCase span {
  color: #9ca3af;
  margin-top: 4px;
}

.ragBox li {
  margin-bottom: 8px;
  color: #cbd5e1;
}

@media (max-width: 900px) {
  .buttonRow {
    grid-template-columns: 1fr;
  }
}
"""

if css_path.exists():
    current_css = css_path.read_text(encoding="utf-8")
    if ".ragBox" not in current_css:
        css_path.write_text(current_css.rstrip() + extra_css + "\n", encoding="utf-8")
        print("updated: frontend/src/styles.css")
    else:
        print("skipped: frontend/src/styles.css already has Agentic RAG styles")

readme = ROOT / "README.md"
if readme.exists():
    current = readme.read_text(encoding="utf-8")
    section = r"""

## Agentic RAG Upgrade

This version includes an Agentic RAG assignment path:

```txt
POST /assign/agentic
```

Flow:

```txt
Task input
↓
Task parser detects category, priority, and skills
↓
RAG retrieves similar past cases from data/past_cases.csv
↓
RAG retrieves relevant SOP/policy context from data/knowledge_base/support_policy.txt
↓
Scoring engine checks idle status, shift timing, workload, skills, and performance
↓
RAG bonus adjusts score using similar-case success/escalation evidence
↓
System returns final assignment with explanation and retrieved evidence
```

The LLM/agent layer should not blindly decide the final assignment.  
The scoring/scheduling engine remains the final decision layer so the system is auditable.
"""
    if "## Agentic RAG Upgrade" not in current:
        readme.write_text(current.rstrip() + section + "\n", encoding="utf-8")
        print("updated: README.md")

print("\nAgentic RAG upgrade added successfully.")
print("Backend should auto-reload. Frontend should hot-refresh.")
print("New endpoint: POST /assign/agentic")
print("If reload fails, restart backend and frontend.")
