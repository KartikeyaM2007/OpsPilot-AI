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
  onGenerateMockTask,
  selectedModelType,
  loading,
  agenticLoading,
  mlLoading,
  mockTaskLoading,
}) {
  const [task, setTask] = useState(DEFAULT_TASK);

  function updateField(field, value) {
    setTask((current) => ({
      ...current,
      [field]: value,
    }));
  }

  async function fillMockTask() {
    const mock = await onGenerateMockTask();
    if (!mock) return;

    setTask({
      title: mock.title || "",
      description: mock.description || "",
      priority: mock.priority || "medium",
      category: mock.category || "general",
      required_skills: Array.isArray(mock.required_skills)
        ? mock.required_skills.join(",")
        : String(mock.required_skills || ""),
      sla_minutes: mock.sla_minutes || 120,
    });
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
    onMlAssign(buildPayload(), selectedModelType);
  }

  const disabled = loading || agenticLoading || mlLoading || mockTaskLoading;

  return (
    <div className="card">
      <div className="formHeader">
        <div>
          <h2>Assign a Custom Task</h2>
          <p className="muted">
            Normal uses scoring. Agentic RAG retrieves evidence. ML assignment uses the selected ML strategy.
          </p>
        </div>

        <button
          type="button"
          className="mockButton"
          disabled={disabled}
          onClick={fillMockTask}
        >
          {mockTaskLoading ? "Generating..." : "Generate Mock Task"}
        </button>
      </div>

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
            {mlLoading ? "Running ML..." : `ML Assignment (${selectedModelType.replaceAll("_", " ")})`}
          </button>
        </div>
      </form>
    </div>
  );
}
