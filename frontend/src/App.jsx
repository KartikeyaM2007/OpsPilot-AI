import { useEffect, useState } from "react";

import { apiDelete, apiGet, apiPost } from "./api/client";
import AssignmentCard from "./components/AssignmentCard";
import AssignmentHistory from "./components/AssignmentHistory";
import Dashboard from "./components/Dashboard";
import LLMPanel from "./components/LLMPanel";
import MLPanel from "./components/MLPanel";
import ResourceForm from "./components/ResourceForm";
import ResourceTable from "./components/ResourceTable";
import TaskForm from "./components/TaskForm";
import TaskTable from "./components/TaskTable";
import TerminalPanel from "./components/TerminalPanel";

function SingleAssignmentResult({ result }) {
  if (!result) return null;

  const title =
    result.mode === "agentic_rag"
      ? "Agentic RAG Assignment Result"
      : result.mode === "ml_ranker" || result.mode === "ml_ranker_fallback"
        ? "ML Strategy Assignment Result"
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
  const [llmStatus, setLlmStatus] = useState(null);
  const [analytics, setAnalytics] = useState(null);
  const [selectedModelType, setSelectedModelType] = useState("lightgbm_ranker");
  const [batchResult, setBatchResult] = useState(null);
  const [singleResult, setSingleResult] = useState(null);
  const [now, setNow] = useState("10:30");
  const [loadingBatch, setLoadingBatch] = useState(false);
  const [loadingSingle, setLoadingSingle] = useState(false);
  const [loadingAgentic, setLoadingAgentic] = useState(false);
  const [loadingMl, setLoadingMl] = useState(false);
  const [loadingTrain, setLoadingTrain] = useState(false);
  const [loadingResource, setLoadingResource] = useState(false);
  const [loadingMockTask, setLoadingMockTask] = useState(false);
  const [loadingMockResource, setLoadingMockResource] = useState(false);
  const [error, setError] = useState("");

  async function loadData() {
    try {
      const [resourceData, taskData, logsData, mlData, analyticsData, llmData] = await Promise.all([
        apiGet("/resources"),
        apiGet("/tasks"),
        apiGet("/assignment-logs"),
        apiGet("/ml/status"),
        apiGet("/analytics/summary"),
        apiGet("/llm/status"),
      ]);

      setResources(resourceData);
      setTasks(taskData);
      setAssignmentLogs(logsData);
      setMlStatus(mlData);
      setAnalytics(analyticsData);
      setLlmStatus(llmData);

      const trainedType = mlData?.metadata?.requested_model_type;
      if (trainedType) {
        setSelectedModelType(trainedType);
      }
    } catch (err) {
      setError(err.message);
    }
  }

  async function refreshRuntimeData() {
    try {
      const [logsData, mlData, analyticsData, llmData] = await Promise.all([
        apiGet("/assignment-logs"),
        apiGet("/ml/status"),
        apiGet("/analytics/summary"),
        apiGet("/llm/status"),
      ]);
      setAssignmentLogs(logsData);
      setMlStatus(mlData);
      setAnalytics(analyticsData);
      setLlmStatus(llmData);
    } catch (err) {
      setError(err.message);
    }
  }

  async function generateMockTask() {
    setLoadingMockTask(true);
    setError("");

    try {
      const data = await apiPost("/mock/task?provider=ollama");
      if (!data.llm_used && data.fallback_reason) {
        setError(`Mock task used fallback: ${data.fallback_reason}`);
      }
      return data;
    } catch (err) {
      setError(err.message);
      return null;
    } finally {
      setLoadingMockTask(false);
    }
  }

  async function generateMockResource() {
    setLoadingMockResource(true);
    setError("");

    try {
      const data = await apiPost("/mock/resource?provider=ollama");
      if (!data.llm_used && data.fallback_reason) {
        setError(`Mock resource used fallback: ${data.fallback_reason}`);
      }
      return data;
    } catch (err) {
      setError(err.message);
      return null;
    } finally {
      setLoadingMockResource(false);
    }
  }

  async function trainMlRanker(modelType) {
    setLoadingTrain(true);
    setError("");

    try {
      const data = await apiPost(`/ml/train?model_type=${encodeURIComponent(modelType)}`);
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

  async function runMlAssignment(taskPayload, modelType) {
    setLoadingMl(true);
    setError("");

    try {
      const data = await apiPost(
        `/assign/ml?now_hhmm=${encodeURIComponent(now)}&model_type=${encodeURIComponent(modelType)}`,
        taskPayload
      );
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
            workflow traces, assignment history, selectable ML models, SQLite, analytics,
            live backend telemetry, and optional LLM providers.
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
        <TerminalPanel />

        <Dashboard analytics={analytics} />
        <LLMPanel status={llmStatus} />

        <TaskForm
          onAssign={runCustomAssignment}
          onAgenticAssign={runAgenticAssignment}
          onMlAssign={runMlAssignment}
          onGenerateMockTask={generateMockTask}
          selectedModelType={selectedModelType}
          loading={loadingSingle}
          agenticLoading={loadingAgentic}
          mlLoading={loadingMl}
          mockTaskLoading={loadingMockTask}
        />

        <SingleAssignmentResult result={singleResult} />

        <MLPanel
          status={mlStatus}
          selectedModelType={selectedModelType}
          onModelTypeChange={setSelectedModelType}
          onTrain={trainMlRanker}
          loading={loadingTrain}
        />

        <AssignmentHistory logs={assignmentLogs} />

        <ResourceForm
          onCreate={createResource}
          onGenerateMockResource={generateMockResource}
          loading={loadingResource}
          mockResourceLoading={loadingMockResource}
        />
        <ResourceTable resources={resources} onDelete={deleteResource} />

        <TaskTable tasks={tasks} />

        <BatchAssignmentResult result={batchResult} />
      </section>
    </main>
  );
}
