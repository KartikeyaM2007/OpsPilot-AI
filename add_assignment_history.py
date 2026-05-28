from pathlib import Path

ROOT = Path(__file__).resolve().parent

def write_file(relative_path: str, content: str):
    path = ROOT / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.strip() + "\n", encoding="utf-8")
    print(f"updated: {relative_path}")

write_file("backend/app/database.py", r"""
import csv
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


DATA_DIR = Path(__file__).resolve().parents[2] / "data"
ASSIGNMENT_LOG_PATH = DATA_DIR / "assignment_logs.csv"


def _split_list(value: Any) -> List[str]:
    if value is None:
        return []
    return [item.strip().lower() for item in str(value).split(";") if item.strip()]


def _join_list(value: Any) -> str:
    if isinstance(value, list):
        return ";".join(str(item) for item in value)
    return str(value or "")


def _read_csv(filename: str) -> List[Dict[str, Any]]:
    path = DATA_DIR / filename
    if not path.exists():
        return []

    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def load_tasks() -> List[Dict[str, Any]]:
    rows = _read_csv("sample_tasks.csv")
    for row in rows:
        row["required_skills"] = _split_list(row.get("required_skills"))
        row["sla_minutes"] = int(row.get("sla_minutes") or 120)
    return rows


def load_resources() -> List[Dict[str, Any]]:
    rows = _read_csv("sample_resources.csv")
    for row in rows:
        row["skills"] = _split_list(row.get("skills"))
        row["handled_categories"] = _split_list(row.get("handled_categories"))
        row["experience_level"] = int(row.get("experience_level") or 1)
        row["current_tasks"] = int(row.get("current_tasks") or 0)
        row["max_tasks"] = int(row.get("max_tasks") or 3)
        row["success_rate"] = float(row.get("success_rate") or 0.5)
        row["avg_resolution_minutes"] = float(row.get("avg_resolution_minutes") or 120)
        row["status"] = str(row.get("status") or "offline").lower()
    return rows


def load_history() -> List[Dict[str, Any]]:
    return _read_csv("task_history.csv")


def save_resources(resources: List[Dict[str, Any]]) -> None:
    path = DATA_DIR / "sample_resources.csv"
    path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "resource_id",
        "name",
        "skills",
        "experience_level",
        "status",
        "current_tasks",
        "max_tasks",
        "shift_start",
        "shift_end",
        "success_rate",
        "avg_resolution_minutes",
        "handled_categories",
    ]

    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()

        for resource in resources:
            row = dict(resource)
            row["skills"] = _join_list(row.get("skills"))
            row["handled_categories"] = _join_list(row.get("handled_categories"))
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def load_assignment_logs(limit: int = 50) -> List[Dict[str, Any]]:
    if not ASSIGNMENT_LOG_PATH.exists():
        return []

    with ASSIGNMENT_LOG_PATH.open("r", encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))

    rows.reverse()
    return rows[:limit]


def append_assignment_log(result: Dict[str, Any]) -> Dict[str, Any]:
    ASSIGNMENT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    task = result.get("task", {}) or {}
    assigned_resource = result.get("assigned_resource") or {}

    fieldnames = [
        "log_id",
        "timestamp",
        "mode",
        "task_title",
        "task_category",
        "task_priority",
        "required_skills",
        "assigned",
        "assigned_resource",
        "score",
        "base_score",
        "rag_bonus",
        "explanation",
    ]

    log_row = {
        "log_id": datetime.now().strftime("%Y%m%d%H%M%S%f"),
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "mode": result.get("mode") or "normal_scoring",
        "task_title": task.get("title", ""),
        "task_category": task.get("category", ""),
        "task_priority": task.get("priority", ""),
        "required_skills": ", ".join(task.get("required_skills", []) or []),
        "assigned": result.get("assigned", False),
        "assigned_resource": assigned_resource.get("name", "") if assigned_resource else "",
        "score": assigned_resource.get("score", "") if assigned_resource else "",
        "base_score": assigned_resource.get("base_score", "") if assigned_resource else "",
        "rag_bonus": assigned_resource.get("rag_bonus", "") if assigned_resource else "",
        "explanation": result.get("explanation", ""),
    }

    file_exists = ASSIGNMENT_LOG_PATH.exists()

    with ASSIGNMENT_LOG_PATH.open("a", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerow(log_row)

    return log_row
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
from .schemas import AssignmentRequest, ResourceIn, TaskIn


app = FastAPI(
    title="AI Task Allocation System",
    description="Smart workforce task allocation using availability, shift timing, workload, skills, past performance, Agentic RAG, and assignment history logging.",
    version="1.3.0",
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


@app.get("/assignment-logs")
def get_assignment_logs(limit: int = Query(default=50, ge=1, le=500)):
    return load_assignment_logs(limit=limit)


@app.post("/assign")
def assign_task(task: TaskIn, now_hhmm: Optional[str] = Query(default=None)):
    result = assign_single_task(task.model_dump(), now_hhmm=now_hhmm)
    append_assignment_log(result)
    return result


@app.post("/assign/agentic")
def assign_task_with_agentic_rag(task: TaskIn, now_hhmm: Optional[str] = Query(default=None)):
    result = assign_task_agentic(task.model_dump(), now_hhmm=now_hhmm)
    append_assignment_log(result)
    return result


@app.post("/assign/batch")
def assign_batch(payload: AssignmentRequest):
    result = assign_tasks(
        [task.model_dump() for task in payload.tasks],
        now_hhmm=payload.now_hhmm,
    )

    for item in result.get("assignments", []):
        append_assignment_log(item)

    return result


@app.post("/assign/sample")
def assign_sample(now_hhmm: Optional[str] = Query(default="10:30")):
    result = assign_tasks(load_tasks(), now_hhmm=now_hhmm)

    for item in result.get("assignments", []):
        append_assignment_log(item)

    return result
""")

write_file("frontend/src/components/AssignmentHistory.jsx", r"""
export default function AssignmentHistory({ logs }) {
  return (
    <div className="card">
      <h2>Assignment History</h2>
      <p className="muted">
        Every normal and Agentic RAG assignment is logged here. This becomes training data for the future ML ranking model.
      </p>

      {logs.length === 0 ? (
        <div className="emptyState">
          No assignments logged yet. Run Normal Assignment or Agentic RAG Assignment first.
        </div>
      ) : (
        <div className="historyList">
          {logs.map((log) => (
            <div className="historyItem" key={log.log_id}>
              <div className="historyTop">
                <div>
                  <strong>{log.task_title}</strong>
                  <span>
                    {log.task_category} • {log.task_priority} • {log.mode}
                  </span>
                </div>

                <div className="historyScore">
                  <b>{log.assigned_resource || "Unassigned"}</b>
                  <span>{log.score ? `Score ${log.score}` : "No score"}</span>
                </div>
              </div>

              <p>{log.explanation}</p>

              <div className="historyMeta">
                <span>{log.timestamp}</span>
                <span>Skills: {log.required_skills}</span>
                {log.rag_bonus && <span>RAG bonus: {log.rag_bonus}</span>}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
""")

write_file("frontend/src/App.jsx", r"""
import { useEffect, useState } from "react";

import { apiDelete, apiGet, apiPost } from "./api/client";
import AssignmentCard from "./components/AssignmentCard";
import AssignmentHistory from "./components/AssignmentHistory";
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
  const [assignmentLogs, setAssignmentLogs] = useState([]);
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
      const [resourceData, taskData, logsData] = await Promise.all([
        apiGet("/resources"),
        apiGet("/tasks"),
        apiGet("/assignment-logs"),
      ]);

      setResources(resourceData);
      setTasks(taskData);
      setAssignmentLogs(logsData);
    } catch (err) {
      setError(err.message);
    }
  }

  async function refreshLogs() {
    try {
      const logsData = await apiGet("/assignment-logs");
      setAssignmentLogs(logsData);
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
      await refreshLogs();
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
      await refreshLogs();
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
      await refreshLogs();
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
            workload constraints, Agentic RAG retrieval, explainable workflow traces, and assignment history.
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

.emptyState {
  border: 1px dashed #334155;
  border-radius: 14px;
  padding: 18px;
  color: #9ca3af;
  background: #0f172a;
}

.historyList {
  display: grid;
  gap: 12px;
  margin-top: 14px;
}

.historyItem {
  border: 1px solid #263244;
  border-radius: 14px;
  padding: 14px;
  background: #0f172a;
}

.historyTop {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: start;
}

.historyTop strong,
.historyTop span,
.historyScore b,
.historyScore span {
  display: block;
}

.historyTop strong {
  color: #dbeafe;
  font-size: 15px;
}

.historyTop span,
.historyScore span {
  color: #9ca3af;
  margin-top: 4px;
}

.historyScore {
  text-align: right;
  min-width: 140px;
}

.historyScore b {
  color: #a7f3d0;
}

.historyItem p {
  color: #cbd5e1;
  line-height: 1.5;
  margin: 10px 0;
}

.historyMeta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.historyMeta span {
  border-radius: 999px;
  padding: 5px 8px;
  background: #111827;
  color: #93c5fd;
  font-size: 12px;
}

@media (max-width: 900px) {
  .historyTop {
    flex-direction: column;
  }

  .historyScore {
    text-align: left;
  }
}
"""

if css_path.exists():
    current_css = css_path.read_text(encoding="utf-8")
    if ".historyList" not in current_css:
        css_path.write_text(current_css.rstrip() + extra_css + "\n", encoding="utf-8")
        print("updated: frontend/src/styles.css")
    else:
        print("skipped: frontend/src/styles.css already has assignment history styles")

readme = ROOT / "README.md"
if readme.exists():
    current = readme.read_text(encoding="utf-8")
    section = r"""

## Assignment History Logging

The system now logs every assignment to:

```txt
data/assignment_logs.csv
```

Logged fields include:

```txt
mode
task title
category
priority
required skills
assigned resource
final score
base score
RAG bonus
explanation
timestamp
```

This assignment log becomes the future training dataset for the ML ranking model.
"""
    if "## Assignment History Logging" not in current:
        readme.write_text(current.rstrip() + section + "\n", encoding="utf-8")
        print("updated: README.md")

print("\nAssignment history upgrade added successfully.")
print("Backend should auto-reload. Frontend should hot-refresh.")
print("New endpoint: GET /assignment-logs")
print("Run Normal Assignment or Agentic RAG Assignment to create logs.")
