from pathlib import Path

ROOT = Path(__file__).resolve().parent

def write_file(relative_path: str, content: str):
    path = ROOT / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.strip() + "\n", encoding="utf-8")
    print(f"updated: {relative_path}")

write_file("backend/app/schemas.py", r"""
from typing import List, Optional
from pydantic import BaseModel, Field


class TaskIn(BaseModel):
    task_id: str = ""
    title: str
    description: str = ""
    priority: str = "medium"
    category: Optional[str] = None
    required_skills: List[str] = Field(default_factory=list)
    sla_minutes: int = 120


class AssignmentRequest(BaseModel):
    tasks: List[TaskIn]
    now_hhmm: Optional[str] = None


class ResourceIn(BaseModel):
    resource_id: str = ""
    name: str
    skills: List[str] = Field(default_factory=list)
    experience_level: int = Field(default=3, ge=1, le=5)
    status: str = "idle"
    current_tasks: int = Field(default=0, ge=0)
    max_tasks: int = Field(default=3, ge=1)
    shift_start: str = "09:00"
    shift_end: str = "18:00"
    success_rate: float = Field(default=0.85, ge=0, le=1)
    avg_resolution_minutes: float = Field(default=60, ge=1)
    handled_categories: List[str] = Field(default_factory=list)
""")

write_file("backend/app/main.py", r"""
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .assignment_engine import assign_single_task, assign_tasks
from .database import load_history, load_resources, load_tasks, save_resources
from .schemas import AssignmentRequest, ResourceIn, TaskIn


app = FastAPI(
    title="AI Task Allocation System",
    description="Smart workforce task allocation using availability, shift timing, workload, skills, and past performance.",
    version="1.1.0",
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

write_file("frontend/src/api/client.js", r"""
const API_BASE = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";

export async function apiGet(path) {
  const response = await fetch(`${API_BASE}${path}`);
  if (!response.ok) {
    throw new Error(`GET ${path} failed`);
  }
  return response.json();
}

export async function apiPost(path, body = null) {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: body ? JSON.stringify(body) : null,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || `POST ${path} failed`);
  }

  return response.json();
}

export async function apiPut(path, body = null) {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
    },
    body: body ? JSON.stringify(body) : null,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || `PUT ${path} failed`);
  }

  return response.json();
}

export async function apiDelete(path) {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "DELETE",
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || `DELETE ${path} failed`);
  }

  return response.json();
}
""")

write_file("frontend/src/components/ResourceForm.jsx", r"""
import { useState } from "react";

const DEFAULT_RESOURCE = {
  name: "Sara",
  status: "idle",
  current_tasks: 0,
  max_tasks: 3,
  shift_start: "09:00",
  shift_end: "18:00",
  skills: "billing,payments,customer_support",
  handled_categories: "payment,billing",
  experience_level: 3,
  success_rate_percent: 88,
  avg_resolution_minutes: 45,
};

export default function ResourceForm({ onCreate, loading }) {
  const [resource, setResource] = useState(DEFAULT_RESOURCE);

  function updateField(field, value) {
    setResource((current) => ({
      ...current,
      [field]: value,
    }));
  }

  function splitCsv(value) {
    return value
      .split(",")
      .map((item) => item.trim().toLowerCase())
      .filter(Boolean);
  }

  function submitResource(event) {
    event.preventDefault();

    const payload = {
      resource_id: "",
      name: resource.name.trim(),
      status: resource.status,
      current_tasks: Number(resource.current_tasks) || 0,
      max_tasks: Number(resource.max_tasks) || 1,
      shift_start: resource.shift_start,
      shift_end: resource.shift_end,
      skills: splitCsv(resource.skills),
      handled_categories: splitCsv(resource.handled_categories),
      experience_level: Number(resource.experience_level) || 3,
      success_rate: Math.min(Math.max(Number(resource.success_rate_percent) || 85, 0), 100) / 100,
      avg_resolution_minutes: Number(resource.avg_resolution_minutes) || 60,
    };

    onCreate(payload);

    setResource((current) => ({
      ...current,
      name: "",
    }));
  }

  return (
    <div className="card">
      <h2>Add Resource / Agent</h2>
      <p className="muted">
        Add a new support agent with skill, shift, workload, status, and performance data.
      </p>

      <form className="taskForm" onSubmit={submitResource}>
        <div className="formGrid">
          <label>
            Name
            <input
              value={resource.name}
              onChange={(event) => updateField("name", event.target.value)}
              placeholder="Agent name"
              required
            />
          </label>

          <label>
            Status
            <select
              value={resource.status}
              onChange={(event) => updateField("status", event.target.value)}
            >
              <option value="idle">idle</option>
              <option value="available">available</option>
              <option value="busy">busy</option>
              <option value="offline">offline</option>
            </select>
          </label>

          <label>
            Experience 1-5
            <input
              type="number"
              min="1"
              max="5"
              value={resource.experience_level}
              onChange={(event) => updateField("experience_level", event.target.value)}
            />
          </label>
        </div>

        <div className="formGrid">
          <label>
            Current tasks
            <input
              type="number"
              min="0"
              value={resource.current_tasks}
              onChange={(event) => updateField("current_tasks", event.target.value)}
            />
          </label>

          <label>
            Max tasks
            <input
              type="number"
              min="1"
              value={resource.max_tasks}
              onChange={(event) => updateField("max_tasks", event.target.value)}
            />
          </label>

          <label>
            Success %
            <input
              type="number"
              min="0"
              max="100"
              value={resource.success_rate_percent}
              onChange={(event) => updateField("success_rate_percent", event.target.value)}
            />
          </label>
        </div>

        <div className="formGrid">
          <label>
            Shift start
            <input
              type="time"
              value={resource.shift_start}
              onChange={(event) => updateField("shift_start", event.target.value)}
            />
          </label>

          <label>
            Shift end
            <input
              type="time"
              value={resource.shift_end}
              onChange={(event) => updateField("shift_end", event.target.value)}
            />
          </label>

          <label>
            Avg resolution minutes
            <input
              type="number"
              min="1"
              value={resource.avg_resolution_minutes}
              onChange={(event) => updateField("avg_resolution_minutes", event.target.value)}
            />
          </label>
        </div>

        <label>
          Skills
          <input
            value={resource.skills}
            onChange={(event) => updateField("skills", event.target.value)}
            placeholder="billing,payments,customer_support"
          />
        </label>

        <label>
          Handled categories
          <input
            value={resource.handled_categories}
            onChange={(event) => updateField("handled_categories", event.target.value)}
            placeholder="payment,billing,technical"
          />
        </label>

        <button type="submit" disabled={loading}>
          {loading ? "Adding..." : "Add Resource"}
        </button>
      </form>
    </div>
  );
}
""")

write_file("frontend/src/components/ResourceTable.jsx", r"""
export default function ResourceTable({ resources, onDelete }) {
  return (
    <div className="card">
      <h2>Resources / Agents</h2>
      <div className="tableWrap">
        <table>
          <thead>
            <tr>
              <th>Name</th>
              <th>Status</th>
              <th>Workload</th>
              <th>Shift</th>
              <th>Skills</th>
              <th>Success</th>
              {onDelete && <th>Action</th>}
            </tr>
          </thead>
          <tbody>
            {resources.map((resource) => (
              <tr key={resource.resource_id}>
                <td>
                  <strong>{resource.name}</strong>
                  <div className="muted">{resource.resource_id}</div>
                </td>
                <td>
                  <span className={`pill ${resource.status}`}>{resource.status}</span>
                </td>
                <td>{resource.current_tasks}/{resource.max_tasks}</td>
                <td>{resource.shift_start} - {resource.shift_end}</td>
                <td>{resource.skills?.join(", ")}</td>
                <td>{Math.round(Number(resource.success_rate) * 100)}%</td>
                {onDelete && (
                  <td>
                    <button
                      className="miniDanger"
                      onClick={() => onDelete(resource.resource_id)}
                    >
                      Delete
                    </button>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
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
      <h2>Custom Task Assignment Result</h2>
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

  useEffect(() => {
    loadData();
  }, []);

  return (
    <main className="app">
      <section className="hero">
        <div>
          <h1>AI Task Allocation System</h1>
          <p>
            Assign service/support tasks to the most suitable available resource using
            idle status, shift timing, workload, skill match, experience, and past performance.
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
        <TaskForm onAssign={runCustomAssignment} loading={loadingSingle} />
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

.miniDanger {
  padding: 7px 10px;
  border-radius: 9px;
  background: #7f1d1d;
  color: #fecaca;
  font-size: 12px;
}

.miniDanger:hover {
  background: #991b1b;
}
"""

if css_path.exists():
    current_css = css_path.read_text(encoding="utf-8")
    if ".miniDanger" not in current_css:
        css_path.write_text(current_css.rstrip() + extra_css + "\n", encoding="utf-8")
        print("updated: frontend/src/styles.css")
    else:
        print("skipped: frontend/src/styles.css already has resource manager styles")

print("\nResource manager upgrade added successfully.")
print("Backend should auto-reload. Frontend should hot-refresh.")
print("If needed, restart backend and frontend.")
