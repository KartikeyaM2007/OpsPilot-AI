from pathlib import Path

ROOT = Path(__file__).resolve().parent

def write_file(relative_path: str, content: str):
    path = ROOT / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.strip() + "\n", encoding="utf-8")
    print(f"updated: {relative_path}")

write_file("backend/app/analytics_engine.py", r"""
from collections import Counter
from typing import Dict, List

from .database import load_assignment_logs, load_resources
from .ml_ranking_model import get_ml_status


def _safe_int(value, default=0):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def build_analytics_summary(limit: int = 500) -> Dict:
    resources = load_resources()
    logs = load_assignment_logs(limit=limit)
    ml_status = get_ml_status()

    total_resources = len(resources)
    idle_resources = sum(1 for item in resources if item.get("status") == "idle")
    available_resources = sum(1 for item in resources if item.get("status") == "available")
    busy_resources = sum(1 for item in resources if item.get("status") == "busy")
    offline_resources = sum(1 for item in resources if item.get("status") == "offline")

    total_capacity = sum(_safe_int(item.get("max_tasks")) for item in resources)
    used_capacity = sum(_safe_int(item.get("current_tasks")) for item in resources)
    workload_percent = round((used_capacity / total_capacity) * 100, 2) if total_capacity else 0

    assigned_logs = [item for item in logs if str(item.get("assigned", "")).lower() == "true"]
    total_assignments = len(logs)

    resource_counter = Counter(item.get("assigned_resource") or "Unassigned" for item in logs)
    category_counter = Counter(item.get("task_category") or "unknown" for item in logs)
    mode_counter = Counter(item.get("mode") or "unknown" for item in logs)
    priority_counter = Counter(item.get("task_priority") or "unknown" for item in logs)

    scores = [
        _safe_float(item.get("score"))
        for item in logs
        if str(item.get("score", "")).strip()
    ]
    avg_score = round(sum(scores) / len(scores), 2) if scores else 0

    resource_workload = []
    for resource in resources:
        current_tasks = _safe_int(resource.get("current_tasks"))
        max_tasks = max(_safe_int(resource.get("max_tasks"), 1), 1)
        resource_workload.append({
            "name": resource.get("name"),
            "status": resource.get("status"),
            "current_tasks": current_tasks,
            "max_tasks": max_tasks,
            "workload_percent": round((current_tasks / max_tasks) * 100, 2),
            "success_rate": round(_safe_float(resource.get("success_rate")) * 100, 2),
        })

    return {
        "summary": {
            "total_resources": total_resources,
            "idle_resources": idle_resources,
            "available_resources": available_resources,
            "busy_resources": busy_resources,
            "offline_resources": offline_resources,
            "total_assignments": total_assignments,
            "assigned_count": len(assigned_logs),
            "avg_assignment_score": avg_score,
            "used_capacity": used_capacity,
            "total_capacity": total_capacity,
            "workload_percent": workload_percent,
            "ml_model_ready": ml_status.get("model_exists", False),
            "ml_training_rows": ml_status.get("training_rows", 0),
        },
        "resource_workload": resource_workload,
        "assignment_distribution": [
            {"label": key, "value": value}
            for key, value in resource_counter.most_common()
        ],
        "category_distribution": [
            {"label": key, "value": value}
            for key, value in category_counter.most_common()
        ],
        "mode_distribution": [
            {"label": key, "value": value}
            for key, value in mode_counter.most_common()
        ],
        "priority_distribution": [
            {"label": key, "value": value}
            for key, value in priority_counter.most_common()
        ],
        "ml_status": ml_status,
    }
""")

write_file("backend/app/main.py", r"""
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .agentic_assignment_engine import assign_task_agentic
from .analytics_engine import build_analytics_summary
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
    description="Smart workforce task allocation using deterministic scoring, Agentic RAG, workflow traces, assignment history, trainable ML ranking, and analytics.",
    version="1.5.0",
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


@app.get("/analytics/summary")
def analytics_summary(limit: int = Query(default=500, ge=1, le=2000)):
    return build_analytics_summary(limit=limit)


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

write_file("frontend/src/components/Dashboard.jsx", r"""
function StatCard({ label, value, hint }) {
  return (
    <div className="statCard">
      <b>{value}</b>
      <span>{label}</span>
      {hint && <small>{hint}</small>}
    </div>
  );
}

function BarList({ title, items }) {
  const maxValue = Math.max(...items.map((item) => Number(item.value) || 0), 1);

  return (
    <div className="dashPanel">
      <h3>{title}</h3>

      {items.length === 0 ? (
        <p className="muted">No data yet.</p>
      ) : (
        <div className="barList">
          {items.map((item) => {
            const width = Math.round((Number(item.value) / maxValue) * 100);

            return (
              <div className="barItem" key={item.label}>
                <div className="barTop">
                  <span>{item.label}</span>
                  <b>{item.value}</b>
                </div>
                <div className="barTrack">
                  <div className="barFill" style={{ width: `${width}%` }} />
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function WorkloadPanel({ resources }) {
  return (
    <div className="dashPanel">
      <h3>Resource Workload</h3>

      <div className="barList">
        {resources.map((resource) => (
          <div className="barItem" key={resource.name}>
            <div className="barTop">
              <span>
                {resource.name}{" "}
                <small className={`tinyStatus ${resource.status}`}>{resource.status}</small>
              </span>
              <b>
                {resource.current_tasks}/{resource.max_tasks}
              </b>
            </div>
            <div className="barTrack">
              <div className="barFill" style={{ width: `${resource.workload_percent}%` }} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function Dashboard({ analytics }) {
  if (!analytics) return null;

  const summary = analytics.summary || {};
  const mlMetadata = analytics.ml_status?.metadata || {};

  return (
    <div className="card dashboardCard">
      <div className="dashboardHeader">
        <div>
          <h2>Analytics Dashboard</h2>
          <p className="muted">
            Live overview of workforce capacity, assignment distribution, RAG/ML usage, and model readiness.
          </p>
        </div>

        <div className={`modelBadge ${summary.ml_model_ready ? "ready" : "notReady"}`}>
          {summary.ml_model_ready ? "ML Model Ready" : "ML Model Not Trained"}
        </div>
      </div>

      <div className="statGrid">
        <StatCard label="Resources" value={summary.total_resources || 0} />
        <StatCard label="Idle" value={summary.idle_resources || 0} />
        <StatCard label="Busy" value={summary.busy_resources || 0} />
        <StatCard label="Offline" value={summary.offline_resources || 0} />
        <StatCard label="Assignments" value={summary.total_assignments || 0} />
        <StatCard label="Avg Score" value={summary.avg_assignment_score || 0} />
        <StatCard
          label="Capacity Used"
          value={`${summary.workload_percent || 0}%`}
          hint={`${summary.used_capacity || 0}/${summary.total_capacity || 0} slots`}
        />
        <StatCard label="ML Rows" value={summary.ml_training_rows || 0} />
      </div>

      {mlMetadata.top_features?.length > 0 && (
        <div className="dashPanel wide">
          <h3>Top ML Features</h3>
          <div className="featurePills">
            {mlMetadata.top_features.slice(0, 8).map((item) => (
              <span key={item.feature}>
                {item.feature.replaceAll("_", " ")}: <b>{item.importance}</b>
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="dashboardGrid">
        <WorkloadPanel resources={analytics.resource_workload || []} />
        <BarList title="Assignments by Resource" items={analytics.assignment_distribution || []} />
        <BarList title="Assignments by Category" items={analytics.category_distribution || []} />
        <BarList title="Assignments by Mode" items={analytics.mode_distribution || []} />
        <BarList title="Assignments by Priority" items={analytics.priority_distribution || []} />
      </div>
    </div>
  );
}
""")

write_file("frontend/src/App.jsx", r"""
import { useEffect, useState } from "react";

import { apiDelete, apiGet, apiPost } from "./api/client";
import AssignmentCard from "./components/AssignmentCard";
import AssignmentHistory from "./components/AssignmentHistory";
import Dashboard from "./components/Dashboard";
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
  const [analytics, setAnalytics] = useState(null);
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
      const [resourceData, taskData, logsData, mlData, analyticsData] = await Promise.all([
        apiGet("/resources"),
        apiGet("/tasks"),
        apiGet("/assignment-logs"),
        apiGet("/ml/status"),
        apiGet("/analytics/summary"),
      ]);

      setResources(resourceData);
      setTasks(taskData);
      setAssignmentLogs(logsData);
      setMlStatus(mlData);
      setAnalytics(analyticsData);
    } catch (err) {
      setError(err.message);
    }
  }

  async function refreshRuntimeData() {
    try {
      const [logsData, mlData, analyticsData] = await Promise.all([
        apiGet("/assignment-logs"),
        apiGet("/ml/status"),
        apiGet("/analytics/summary"),
      ]);
      setAssignmentLogs(logsData);
      setMlStatus(mlData);
      setAnalytics(analyticsData);
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
      await refreshRuntimeData();
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
      await refreshRuntimeData();
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
      await refreshRuntimeData();
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
      await refreshRuntimeData();
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
      await refreshRuntimeData();
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
            workflow traces, assignment history, ML ranking, and live analytics.
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
        <Dashboard analytics={analytics} />

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

.dashboardCard {
  overflow: hidden;
}

.dashboardHeader {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: start;
  margin-bottom: 16px;
}

.dashboardHeader h2 {
  margin-bottom: 6px;
}

.modelBadge {
  border-radius: 999px;
  padding: 9px 12px;
  font-weight: 900;
  white-space: nowrap;
}

.modelBadge.ready {
  background: #064e3b;
  color: #a7f3d0;
}

.modelBadge.notReady {
  background: #713f12;
  color: #fde68a;
}

.statGrid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 14px;
}

.statCard {
  border: 1px solid #263244;
  border-radius: 16px;
  padding: 14px;
  background: #0f172a;
}

.statCard b,
.statCard span,
.statCard small {
  display: block;
}

.statCard b {
  color: #93c5fd;
  font-size: 26px;
}

.statCard span {
  color: #e5e7eb;
  margin-top: 4px;
  font-weight: 700;
}

.statCard small {
  color: #9ca3af;
  margin-top: 4px;
}

.dashboardGrid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 14px;
  margin-top: 14px;
}

.dashPanel {
  border: 1px solid #263244;
  border-radius: 16px;
  padding: 14px;
  background: #0f172a;
}

.dashPanel.wide {
  margin-top: 14px;
}

.dashPanel h3 {
  margin: 0 0 12px;
  color: #dbeafe;
}

.barList {
  display: grid;
  gap: 12px;
}

.barTop {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  color: #e5e7eb;
  margin-bottom: 6px;
}

.barTop span {
  font-weight: 700;
}

.barTop b {
  color: #93c5fd;
}

.barTrack {
  height: 10px;
  border-radius: 999px;
  background: #111827;
  overflow: hidden;
  border: 1px solid #263244;
}

.barFill {
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, #60a5fa, #8b5cf6);
}

.tinyStatus {
  display: inline-block;
  margin-left: 6px;
  border-radius: 999px;
  padding: 2px 6px;
  font-size: 10px;
  color: #e5e7eb;
  background: #334155;
}

.tinyStatus.idle {
  background: #064e3b;
  color: #a7f3d0;
}

.tinyStatus.available {
  background: #1e3a8a;
  color: #bfdbfe;
}

.tinyStatus.busy {
  background: #713f12;
  color: #fde68a;
}

.tinyStatus.offline {
  background: #4b5563;
  color: #d1d5db;
}

.featurePills {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.featurePills span {
  border-radius: 999px;
  padding: 7px 10px;
  background: #111827;
  border: 1px solid #263244;
  color: #cbd5e1;
}

.featurePills b {
  color: #a7f3d0;
}

@media (max-width: 900px) {
  .dashboardHeader {
    flex-direction: column;
  }

  .statGrid,
  .dashboardGrid {
    grid-template-columns: 1fr;
  }
}
"""

if css_path.exists():
    current_css = css_path.read_text(encoding="utf-8")
    if ".dashboardCard" not in current_css:
        css_path.write_text(current_css.rstrip() + extra_css + "\n", encoding="utf-8")
        print("updated: frontend/src/styles.css")
    else:
        print("skipped: frontend/src/styles.css already has dashboard styles")

readme = ROOT / "README.md"
if readme.exists():
    current = readme.read_text(encoding="utf-8")
    section = r"""

## Analytics Dashboard

The app now includes a live analytics dashboard.

New endpoint:

```txt
GET /analytics/summary
```

Dashboard includes:

```txt
resource count
idle/busy/offline resource status
capacity used
assignment count
average assignment score
ML model readiness
ML training row count
assignment distribution by resource
assignment distribution by task category
assignment distribution by assignment mode
priority breakdown
resource workload bars
top ML feature importances
```
"""
    if "## Analytics Dashboard" not in current:
        readme.write_text(current.rstrip() + section + "\n", encoding="utf-8")
        print("updated: README.md")

print("\nAnalytics dashboard upgrade added successfully.")
print("Backend should auto-reload. Frontend should hot-refresh.")
print("New endpoint: GET /analytics/summary")
