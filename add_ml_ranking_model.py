from pathlib import Path

ROOT = Path(__file__).resolve().parent

def write_file(relative_path: str, content: str):
    path = ROOT / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.strip() + "\n", encoding="utf-8")
    print(f"updated: {relative_path}")

def append_requirements(lines):
    path = ROOT / "backend" / "requirements.txt"
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    updated = existing.rstrip()
    for line in lines:
        if line not in existing:
            updated += "\n" + line
    path.write_text(updated.strip() + "\n", encoding="utf-8")
    print("updated: backend/requirements.txt")

append_requirements(["scikit-learn", "joblib"])

write_file("backend/app/ml_ranking_model.py", r"""
import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score


DATA_DIR = Path(__file__).resolve().parents[2] / "data"
TRAINING_PATH = DATA_DIR / "ml_training_candidates.csv"
MODEL_DIR = DATA_DIR / "models"
MODEL_PATH = MODEL_DIR / "assignment_ranker.joblib"
METADATA_PATH = MODEL_DIR / "assignment_ranker_metadata.json"

FEATURE_COLUMNS = [
    "priority_value",
    "eligible",
    "base_score",
    "rag_bonus",
    "deterministic_score",
    "skill_match",
    "availability",
    "workload",
    "category_match",
    "past_performance",
    "experience",
    "speed",
    "rejection_count",
]

PRIORITY_VALUE = {
    "urgent": 4,
    "high": 3,
    "medium": 2,
    "low": 1,
}


def _priority_value(priority: str) -> int:
    return PRIORITY_VALUE.get(str(priority).lower(), 2)


def _safe_float(value, default=0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _candidate_to_features(task: Dict, candidate: Dict) -> Dict:
    breakdown = candidate.get("breakdown", {}) or {}

    return {
        "priority_value": _priority_value(task.get("priority")),
        "eligible": 1 if candidate.get("eligible") else 0,
        "base_score": _safe_float(candidate.get("base_score", candidate.get("final_score"))),
        "rag_bonus": _safe_float(candidate.get("rag_bonus")),
        "deterministic_score": _safe_float(candidate.get("base_rag_score", candidate.get("final_score"))),
        "skill_match": _safe_float(breakdown.get("skill_match")),
        "availability": _safe_float(breakdown.get("availability")),
        "workload": _safe_float(breakdown.get("workload")),
        "category_match": _safe_float(breakdown.get("category_match")),
        "past_performance": _safe_float(breakdown.get("past_performance")),
        "experience": _safe_float(breakdown.get("experience")),
        "speed": _safe_float(breakdown.get("speed")),
        "rejection_count": len(candidate.get("rejection_reasons", []) or []),
    }


def append_candidate_training_rows(result: Dict) -> int:
    if not result.get("assigned") or not result.get("assigned_resource"):
        return 0

    candidates = result.get("candidates", []) or []
    if not candidates:
        return 0

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    task = result.get("task", {}) or {}
    assigned_resource_id = result.get("assigned_resource", {}).get("resource_id")
    assigned_resource_name = result.get("assigned_resource", {}).get("name")

    fieldnames = [
        "row_id",
        "timestamp",
        "mode",
        "task_title",
        "task_category",
        "task_priority",
        "candidate_resource_id",
        "candidate_resource_name",
        *FEATURE_COLUMNS,
        "label_selected",
    ]

    file_exists = TRAINING_PATH.exists()
    rows_written = 0

    with TRAINING_PATH.open("a", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)

        if not file_exists:
            writer.writeheader()

        for candidate in candidates:
            features = _candidate_to_features(task, candidate)
            label = int(
                candidate.get("resource_id") == assigned_resource_id
                or candidate.get("resource_name") == assigned_resource_name
            )

            row = {
                "row_id": datetime.now().strftime("%Y%m%d%H%M%S%f"),
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "mode": result.get("mode", "normal_scoring"),
                "task_title": task.get("title", ""),
                "task_category": task.get("category", ""),
                "task_priority": task.get("priority", ""),
                "candidate_resource_id": candidate.get("resource_id", ""),
                "candidate_resource_name": candidate.get("resource_name", ""),
                **features,
                "label_selected": label,
            }

            writer.writerow(row)
            rows_written += 1

    return rows_written


def get_ml_status() -> Dict:
    training_rows = 0
    positive_rows = 0
    negative_rows = 0

    if TRAINING_PATH.exists():
        df = pd.read_csv(TRAINING_PATH)
        training_rows = len(df)
        if "label_selected" in df.columns:
            positive_rows = int((df["label_selected"] == 1).sum())
            negative_rows = int((df["label_selected"] == 0).sum())

    metadata = {}
    if METADATA_PATH.exists():
        metadata = json.loads(METADATA_PATH.read_text(encoding="utf-8"))

    return {
        "model_exists": MODEL_PATH.exists(),
        "training_file_exists": TRAINING_PATH.exists(),
        "training_rows": training_rows,
        "positive_rows": positive_rows,
        "negative_rows": negative_rows,
        "model_path": str(MODEL_PATH),
        "metadata": metadata,
    }


def train_ml_model() -> Dict:
    if not TRAINING_PATH.exists():
        return {
            "trained": False,
            "message": "No candidate training data found yet. Run a few assignments first.",
            "status": get_ml_status(),
        }

    df = pd.read_csv(TRAINING_PATH)

    if len(df) < 4:
        return {
            "trained": False,
            "message": "Not enough candidate rows yet. Run a few more assignments.",
            "status": get_ml_status(),
        }

    if "label_selected" not in df.columns or df["label_selected"].nunique() < 2:
        return {
            "trained": False,
            "message": "Training data needs both selected and non-selected candidates.",
            "status": get_ml_status(),
        }

    for column in FEATURE_COLUMNS:
        if column not in df.columns:
            df[column] = 0

    X = df[FEATURE_COLUMNS].fillna(0)
    y = df["label_selected"].astype(int)

    model = RandomForestClassifier(
        n_estimators=120,
        max_depth=8,
        random_state=42,
        class_weight="balanced",
    )
    model.fit(X, y)

    predictions = model.predict(X)
    train_accuracy = float(accuracy_score(y, predictions))

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, MODEL_PATH)

    importances = sorted(
        zip(FEATURE_COLUMNS, model.feature_importances_),
        key=lambda item: item[1],
        reverse=True,
    )

    metadata = {
        "trained_at": datetime.now().isoformat(timespec="seconds"),
        "training_rows": int(len(df)),
        "positive_rows": int((y == 1).sum()),
        "negative_rows": int((y == 0).sum()),
        "train_accuracy": round(train_accuracy, 4),
        "top_features": [
            {"feature": feature, "importance": round(float(value), 4)}
            for feature, value in importances[:8]
        ],
    }

    METADATA_PATH.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    return {
        "trained": True,
        "message": "ML ranking model trained successfully.",
        "metadata": metadata,
        "status": get_ml_status(),
    }


def _load_model():
    if not MODEL_PATH.exists():
        return None
    return joblib.load(MODEL_PATH)


def _predict_candidate_probability(model, task: Dict, candidate: Dict) -> float:
    features = _candidate_to_features(task, candidate)
    X = pd.DataFrame([{column: features.get(column, 0) for column in FEATURE_COLUMNS}])

    if hasattr(model, "predict_proba"):
        return float(model.predict_proba(X)[0][1])

    return float(model.predict(X)[0])


def _append_ml_workflow_step(result: Dict, model_available: bool, winner: Optional[Dict]) -> None:
    trace = result.get("workflow_trace") or []

    trace.append({
        "name": "ML Ranker",
        "status": "completed" if model_available else "fallback",
        "detail": (
            "Trained ML model re-ranked eligible candidates using candidate-level training history."
            if model_available
            else "No trained ML model found, so the system used Agentic RAG scoring as fallback."
        ),
        "data": {
            "model_available": model_available,
            "selected_by_ml": winner.get("resource_name") if winner else None,
            "ml_score": winner.get("ml_score") if winner else None,
        },
    })

    result["workflow_trace"] = trace


def assign_task_ml(task: Dict, now_hhmm: Optional[str] = None) -> Dict:
    from .agentic_assignment_engine import assign_task_agentic

    result = assign_task_agentic(task, now_hhmm=now_hhmm)
    model = _load_model()

    if model is None or not result.get("assigned"):
        result["mode"] = "ml_ranker_fallback"
        result["explanation"] = (
            result.get("explanation", "")
            + " ML ranker fallback was used because no trained model is available yet."
        ).strip()
        _append_ml_workflow_step(result, False, None)
        return result

    task_data = result.get("task", {}) or {}
    candidates = result.get("candidates", []) or []

    for candidate in candidates:
        candidate["base_rag_score"] = candidate.get("final_score", 0)

        if candidate.get("eligible"):
            probability = _predict_candidate_probability(model, task_data, candidate)
            candidate["ml_probability"] = round(probability, 4)
            candidate["ml_score"] = round((probability * 100 * 0.65) + (candidate["base_rag_score"] * 0.35), 2)
            candidate["final_score"] = candidate["ml_score"]
            candidate["positive_reasons"] = candidate.get("positive_reasons", []) + [
                f"ML ranker probability {round(probability * 100, 2)}%"
            ]
        else:
            candidate["ml_probability"] = 0.0
            candidate["ml_score"] = 0.0

    candidates.sort(key=lambda item: item.get("final_score", 0), reverse=True)
    valid_candidates = [candidate for candidate in candidates if candidate.get("eligible")]

    if not valid_candidates:
        result["mode"] = "ml_ranker"
        result["assigned"] = False
        result["assigned_resource"] = None
        _append_ml_workflow_step(result, True, None)
        return result

    winner = valid_candidates[0]

    result["mode"] = "ml_ranker"
    result["candidates"] = candidates
    result["assigned"] = True
    result["assigned_resource"] = {
        "resource_id": winner["resource_id"],
        "name": winner["resource_name"],
        "score": winner["final_score"],
        "base_score": winner.get("base_score"),
        "rag_bonus": winner.get("rag_bonus"),
        "ml_probability": winner.get("ml_probability"),
        "ml_score": winner.get("ml_score"),
    }

    result["explanation"] = (
        f"ML Ranker assigned this task to {winner.get('resource_name')} after using "
        f"Agentic RAG evidence plus the trained candidate-ranking model. "
        f"The selected candidate received ML probability "
        f"{round(winner.get('ml_probability', 0) * 100, 2)}% and blended score "
        f"{winner.get('ml_score')}. "
        f"Original explanation: {result.get('explanation', '')}"
    )

    _append_ml_workflow_step(result, True, winner)
    return result
""")

write_file("backend/app/main.py", r"""
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .agentic_assignment_engine import assign_task_agentic
from .assignment_engine import assign_single_task, assign_tasks
from .database import (
    append_assignment_log,
    load_assignment_logs,
    load_history,
    load_resources,
    load_tasks,
    save_resources,
)
from .ml_ranking_model import (
    append_candidate_training_rows,
    assign_task_ml,
    get_ml_status,
    train_ml_model,
)
from .schemas import AssignmentRequest, ResourceIn, TaskIn


app = FastAPI(
    title="AI Task Allocation System",
    description="Smart workforce task allocation using deterministic scoring, Agentic RAG, workflow traces, assignment history, and trainable ML ranking.",
    version="1.4.0",
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


def _log_result(result):
    append_assignment_log(result)
    append_candidate_training_rows(result)


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


@app.get("/assignment-logs")
def get_assignment_logs(limit: int = Query(default=50, ge=1, le=500)):
    return load_assignment_logs(limit=limit)


@app.get("/ml/status")
def ml_status():
    return get_ml_status()


@app.post("/ml/train")
def ml_train():
    return train_ml_model()


@app.post("/assign")
def assign_task(task: TaskIn, now_hhmm: Optional[str] = Query(default=None)):
    result = assign_single_task(task.model_dump(), now_hhmm=now_hhmm)
    _log_result(result)
    return result


@app.post("/assign/agentic")
def assign_task_with_agentic_rag(task: TaskIn, now_hhmm: Optional[str] = Query(default=None)):
    result = assign_task_agentic(task.model_dump(), now_hhmm=now_hhmm)
    _log_result(result)
    return result


@app.post("/assign/ml")
def assign_task_with_ml_ranker(task: TaskIn, now_hhmm: Optional[str] = Query(default=None)):
    result = assign_task_ml(task.model_dump(), now_hhmm=now_hhmm)
    _log_result(result)
    return result


@app.post("/assign/batch")
def assign_batch(payload: AssignmentRequest):
    result = assign_tasks(
        [task.model_dump() for task in payload.tasks],
        now_hhmm=payload.now_hhmm,
    )

    for item in result.get("assignments", []):
        _log_result(item)

    return result


@app.post("/assign/sample")
def assign_sample(now_hhmm: Optional[str] = Query(default="10:30")):
    result = assign_tasks(load_tasks(), now_hhmm=now_hhmm)

    for item in result.get("assignments", []):
        _log_result(item)

    return result
""")

write_file("frontend/src/components/MLPanel.jsx", r"""
export default function MLPanel({ status, onTrain, loading }) {
  const metadata = status?.metadata || {};
  const topFeatures = metadata.top_features || [];

  return (
    <div className="card">
      <h2>Trainable ML Ranker</h2>
      <p className="muted">
        Candidate-level assignment data is collected automatically. Train the ranker after running a few assignments.
      </p>

      <div className="mlGrid">
        <div>
          <b>{status?.model_exists ? "Ready" : "Not trained"}</b>
          <span>Model status</span>
        </div>
        <div>
          <b>{status?.training_rows || 0}</b>
          <span>Candidate rows</span>
        </div>
        <div>
          <b>{status?.positive_rows || 0}</b>
          <span>Selected rows</span>
        </div>
        <div>
          <b>{status?.negative_rows || 0}</b>
          <span>Rejected rows</span>
        </div>
      </div>

      {metadata.trained_at && (
        <div className="mlMeta">
          <strong>Last trained</strong>
          <span>{metadata.trained_at}</span>
          <strong>Training accuracy</strong>
          <span>{metadata.train_accuracy}</span>
        </div>
      )}

      {topFeatures.length > 0 && (
        <div className="featureList">
          <strong>Top learned features</strong>
          {topFeatures.map((item) => (
            <div key={item.feature}>
              <span>{item.feature.replaceAll("_", " ")}</span>
              <b>{item.importance}</b>
            </div>
          ))}
        </div>
      )}

      <button onClick={onTrain} disabled={loading}>
        {loading ? "Training..." : "Train ML Ranker"}
      </button>
    </div>
  );
}
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

export default function TaskForm({
  onAssign,
  onAgenticAssign,
  onMlAssign,
  loading,
  agenticLoading,
  mlLoading,
}) {
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

  function submitMlTask() {
    onMlAssign(buildPayload());
  }

  const disabled = loading || agenticLoading || mlLoading;

  return (
    <div className="card">
      <h2>Assign a Custom Task</h2>
      <p className="muted">
        Normal assignment uses scoring. Agentic RAG retrieves similar cases and SOPs.
        ML Ranker uses the trained model when available.
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

        <div className="buttonRow three">
          <button type="submit" disabled={disabled}>
            {loading ? "Finding..." : "Normal Assignment"}
          </button>

          <button
            type="button"
            className="secondaryButton"
            disabled={disabled}
            onClick={submitAgenticTask}
          >
            {agenticLoading ? "Running RAG..." : "Agentic RAG Assignment"}
          </button>

          <button
            type="button"
            className="mlButton"
            disabled={disabled}
            onClick={submitMlTask}
          >
            {mlLoading ? "Running ML..." : "ML Ranker Assignment"}
          </button>
        </div>
      </form>
    </div>
  );
}
""")

write_file("frontend/src/components/AssignmentCard.jsx", r"""
import WorkflowTrace from "./WorkflowTrace";

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

function modeLabel(mode) {
  if (mode === "agentic_rag") return "Agentic RAG mode";
  if (mode === "ml_ranker") return "ML Ranker mode";
  if (mode === "ml_ranker_fallback") return "ML Fallback mode";
  return "";
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
            {item.mode ? ` • ${modeLabel(item.mode)}` : ""}
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
            {item.assigned_resource.ml_probability !== undefined && (
              <small>
                ML probability {Math.round(item.assigned_resource.ml_probability * 100)}%
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
            {candidate.ml_probability !== undefined && (
              <small>
                ML prob: {Math.round(candidate.ml_probability * 100)}%
                {candidate.ml_score !== undefined ? ` | ML score: ${candidate.ml_score}` : ""}
              </small>
            )}
            <small>
              {candidate.eligible
                ? candidate.positive_reasons?.slice(0, 2).join(", ")
                : candidate.rejection_reasons?.slice(0, 2).join(", ")}
            </small>
          </div>
        ))}
      </div>

      <WorkflowTrace trace={item.workflow_trace} />
      <RagContext context={item.rag_context} />
    </div>
  );
}
""")

write_file("frontend/src/App.jsx", r"""
import { useEffect, useState } from "react";

import { apiDelete, apiGet, apiPost } from "./api/client";
import AssignmentCard from "./components/AssignmentCard";
import AssignmentHistory from "./components/AssignmentHistory";
import MLPanel from "./components/MLPanel";
import ResourceForm from "./components/ResourceForm";
import ResourceTable from "./components/ResourceTable";
import TaskForm from "./components/TaskForm";
import TaskTable from "./components/TaskTable";

function SingleAssignmentResult({ result }) {
  if (!result) return null;

  const title =
    result.mode === "agentic_rag"
      ? "Agentic RAG Assignment Result"
      : result.mode === "ml_ranker" || result.mode === "ml_ranker_fallback"
        ? "ML Ranker Assignment Result"
        : "Custom Task Assignment Result";

  return (
    <div className="card">
      <h2>{title}</h2>
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
  const [assignmentLogs, setAssignmentLogs] = useState([]);
  const [mlStatus, setMlStatus] = useState(null);
  const [batchResult, setBatchResult] = useState(null);
  const [singleResult, setSingleResult] = useState(null);
  const [now, setNow] = useState("10:30");
  const [loadingBatch, setLoadingBatch] = useState(false);
  const [loadingSingle, setLoadingSingle] = useState(false);
  const [loadingAgentic, setLoadingAgentic] = useState(false);
  const [loadingMl, setLoadingMl] = useState(false);
  const [loadingTrain, setLoadingTrain] = useState(false);
  const [loadingResource, setLoadingResource] = useState(false);
  const [error, setError] = useState("");

  async function loadData() {
    try {
      const [resourceData, taskData, logsData, mlData] = await Promise.all([
        apiGet("/resources"),
        apiGet("/tasks"),
        apiGet("/assignment-logs"),
        apiGet("/ml/status"),
      ]);

      setResources(resourceData);
      setTasks(taskData);
      setAssignmentLogs(logsData);
      setMlStatus(mlData);
    } catch (err) {
      setError(err.message);
    }
  }

  async function refreshLogsAndMl() {
    try {
      const [logsData, mlData] = await Promise.all([
        apiGet("/assignment-logs"),
        apiGet("/ml/status"),
      ]);
      setAssignmentLogs(logsData);
      setMlStatus(mlData);
    } catch (err) {
      setError(err.message);
    }
  }

  async function trainMlRanker() {
    setLoadingTrain(true);
    setError("");

    try {
      const data = await apiPost("/ml/train");
      setMlStatus(data.status || data);
      if (!data.trained) {
        setError(data.message);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoadingTrain(false);
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
      await refreshLogsAndMl();
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
      await refreshLogsAndMl();
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
      await refreshLogsAndMl();
    } catch (err) {
      setError(err.message);
    } finally {
      setLoadingAgentic(false);
    }
  }

  async function runMlAssignment(taskPayload) {
    setLoadingMl(true);
    setError("");

    try {
      const data = await apiPost(`/assign/ml?now_hhmm=${encodeURIComponent(now)}`, taskPayload);
      setSingleResult(data);
      await refreshLogsAndMl();
    } catch (err) {
      setError(err.message);
    } finally {
      setLoadingMl(false);
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
            Assign service/support tasks using deterministic scoring, Agentic RAG retrieval,
            explainable workflow traces, assignment history, and a trainable ML ranker.
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
          onMlAssign={runMlAssignment}
          loading={loadingSingle}
          agenticLoading={loadingAgentic}
          mlLoading={loadingMl}
        />

        <SingleAssignmentResult result={singleResult} />

        <MLPanel status={mlStatus} onTrain={trainMlRanker} loading={loadingTrain} />

        <AssignmentHistory logs={assignmentLogs} />

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

.buttonRow.three {
  grid-template-columns: 1fr 1fr 1fr;
}

.mlButton {
  background: #22c55e;
  color: #052e16;
}

.mlGrid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 14px;
  margin: 14px 0;
}

.mlGrid div {
  border: 1px solid #263244;
  border-radius: 14px;
  padding: 14px;
  background: #0f172a;
}

.mlGrid b,
.mlGrid span {
  display: block;
}

.mlGrid b {
  color: #a7f3d0;
  font-size: 22px;
}

.mlGrid span {
  color: #9ca3af;
  margin-top: 5px;
}

.mlMeta {
  display: grid;
  grid-template-columns: 160px 1fr;
  gap: 8px;
  margin: 14px 0;
  color: #cbd5e1;
}

.mlMeta strong {
  color: #93c5fd;
}

.featureList {
  display: grid;
  gap: 8px;
  margin: 14px 0;
}

.featureList strong {
  color: #dbeafe;
}

.featureList div {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  border-radius: 10px;
  padding: 8px;
  background: #0f172a;
  border: 1px solid #263244;
}

.featureList span {
  color: #cbd5e1;
}

.featureList b {
  color: #a7f3d0;
}

.stepStatus.fallback {
  background: #713f12;
  color: #fde68a;
}

@media (max-width: 900px) {
  .buttonRow.three,
  .mlGrid {
    grid-template-columns: 1fr;
  }

  .mlMeta {
    grid-template-columns: 1fr;
  }
}
"""

if css_path.exists():
    current_css = css_path.read_text(encoding="utf-8")
    if ".mlGrid" not in current_css:
        css_path.write_text(current_css.rstrip() + extra_css + "\n", encoding="utf-8")
        print("updated: frontend/src/styles.css")
    else:
        print("skipped: frontend/src/styles.css already has ML ranker styles")

readme = ROOT / "README.md"
if readme.exists():
    current = readme.read_text(encoding="utf-8")
    section = r"""

## Trainable ML Ranking Model

The project now includes a trainable candidate-ranking model.

New files/endpoints:

```txt
backend/app/ml_ranking_model.py
GET  /ml/status
POST /ml/train
POST /assign/ml
data/ml_training_candidates.csv
data/models/assignment_ranker.joblib
```

How it works:

```txt
1. Every assignment logs all candidate resources.
2. The selected resource gets label_selected = 1.
3. Non-selected candidates get label_selected = 0.
4. /ml/train trains a RandomForest ranking classifier.
5. /assign/ml uses Agentic RAG first, then re-ranks eligible candidates using the trained model.
```

Install the added backend dependencies:

```bash
pip install -r backend/requirements.txt
```
"""
    if "## Trainable ML Ranking Model" not in current:
        readme.write_text(current.rstrip() + section + "\n", encoding="utf-8")
        print("updated: README.md")

print("\nML ranking model upgrade added successfully.")
print("IMPORTANT: install new backend dependencies:")
print("cd backend")
print("pip install -r requirements.txt")
print("Then restart backend if needed.")
print("New endpoints: GET /ml/status, POST /ml/train, POST /assign/ml")
