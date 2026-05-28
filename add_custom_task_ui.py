from pathlib import Path

ROOT = Path(__file__).resolve().parent

def write_file(relative_path: str, content: str):
    path = ROOT / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.strip() + "\n", encoding="utf-8")
    print(f"updated: {relative_path}")

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

export default function TaskForm({ onAssign, loading }) {
  const [task, setTask] = useState(DEFAULT_TASK);

  function updateField(field, value) {
    setTask((current) => ({
      ...current,
      [field]: value,
    }));
  }

  function submitTask(event) {
    event.preventDefault();

    const payload = {
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

    onAssign(payload);
  }

  return (
    <div className="card">
      <h2>Assign a Custom Task</h2>
      <p className="muted">
        Enter a real support/service task and the system will rank all resources, check idle status,
        shift timing, workload, skills, and then choose the best valid agent.
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

        <button type="submit" disabled={loading}>
          {loading ? "Finding Best Agent..." : "Assign This Task"}
        </button>
      </form>
    </div>
  );
}
""")

write_file("frontend/src/App.jsx", r"""
import { useEffect, useState } from "react";

import { apiGet, apiPost } from "./api/client";
import AssignmentCard from "./components/AssignmentCard";
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

        <ResourceTable resources={resources} />
        <TaskTable tasks={tasks} />

        <BatchAssignmentResult result={batchResult} />
      </section>
    </main>
  );
}
""")

# Append extra CSS only if not already present
css_path = ROOT / "frontend/src/styles.css"
extra_css = r"""

.taskForm {
  display: grid;
  gap: 14px;
  margin-top: 16px;
}

.taskForm label {
  display: grid;
  gap: 7px;
  color: #dbeafe;
  font-weight: 700;
}

.taskForm input,
.taskForm textarea,
.taskForm select {
  width: 100%;
  background: #0f172a;
  border: 1px solid #334155;
  color: #e5e7eb;
  border-radius: 12px;
  padding: 12px;
  outline: none;
}

.taskForm input:focus,
.taskForm textarea:focus,
.taskForm select:focus {
  border-color: #60a5fa;
}

.taskForm small {
  color: #9ca3af;
  font-weight: 400;
}

.formGrid {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 14px;
}

@media (max-width: 900px) {
  .formGrid {
    grid-template-columns: 1fr;
  }
}
"""

if css_path.exists():
    current_css = css_path.read_text(encoding="utf-8")
    if ".taskForm" not in current_css:
        css_path.write_text(current_css.rstrip() + extra_css + "\n", encoding="utf-8")
        print("updated: frontend/src/styles.css")
    else:
        print("skipped: frontend/src/styles.css already has task form styles")
else:
    write_file("frontend/src/styles.css", extra_css)

print("\nCustom task UI upgrade added successfully.")
print("Your running Vite frontend should auto-refresh.")
print("If it does not refresh, stop frontend with CTRL+C and run: npm run dev")
