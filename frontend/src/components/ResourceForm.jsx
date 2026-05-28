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

export default function ResourceForm({ onCreate, onGenerateMockResource, loading, mockResourceLoading }) {
  const [resource, setResource] = useState(DEFAULT_RESOURCE);

  function updateField(field, value) {
    setResource((current) => ({
      ...current,
      [field]: value,
    }));
  }

  async function fillMockResource() {
    const mock = await onGenerateMockResource();
    if (!mock) return;

    setResource({
      name: mock.name || "",
      status: mock.status || "idle",
      current_tasks: mock.current_tasks ?? 0,
      max_tasks: mock.max_tasks ?? 3,
      shift_start: mock.shift_start || "09:00",
      shift_end: mock.shift_end || "18:00",
      skills: Array.isArray(mock.skills) ? mock.skills.join(",") : String(mock.skills || ""),
      handled_categories: Array.isArray(mock.handled_categories)
        ? mock.handled_categories.join(",")
        : String(mock.handled_categories || ""),
      experience_level: mock.experience_level || 3,
      success_rate_percent: Math.round(Number(mock.success_rate || 0.85) * 100),
      avg_resolution_minutes: mock.avg_resolution_minutes || 60,
    });
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
      <div className="formHeader">
        <div>
          <h2>Add Resource / Agent</h2>
          <p className="muted">
            Add a new support agent with skill, shift, workload, status, and performance data.
          </p>
        </div>

        <button
          type="button"
          className="mockButton"
          disabled={loading || mockResourceLoading}
          onClick={fillMockResource}
        >
          {mockResourceLoading ? "Generating..." : "Generate Mock Resource"}
        </button>
      </div>

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
