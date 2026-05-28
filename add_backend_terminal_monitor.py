from pathlib import Path

ROOT = Path(__file__).resolve().parent

def write_file(relative_path: str, content: str):
    path = ROOT / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.strip() + '\n', encoding='utf-8')
    print(f'updated: {relative_path}')

FILES = {
    'backend/app/event_logger.py': '\nfrom collections import deque\nfrom datetime import datetime\nfrom typing import Any, Dict, List, Optional\nfrom uuid import uuid4\n\n\n_EVENTS = deque(maxlen=700)\n\n\ndef log_event(\n    source: str,\n    message: str,\n    level: str = "info",\n    data: Optional[Dict[str, Any]] = None,\n) -> Dict[str, Any]:\n    event = {\n        "id": str(uuid4()),\n        "timestamp": datetime.now().isoformat(timespec="seconds"),\n        "level": level,\n        "source": source,\n        "message": message,\n        "data": data or {},\n    }\n\n    _EVENTS.append(event)\n    return event\n\n\ndef get_events(limit: int = 150) -> List[Dict[str, Any]]:\n    limit = max(1, min(int(limit), 700))\n    return list(_EVENTS)[-limit:]\n\n\ndef clear_events() -> None:\n    _EVENTS.clear()\n    log_event("system", "Terminal event stream cleared.", "warning")\n\n\ndef seed_startup_events() -> None:\n    if _EVENTS:\n        return\n\n    log_event("system", "Backend event logger initialized.")\n    log_event("api", "FastAPI application loaded.")\n',
    'backend/app/main.py': '\nimport time\nfrom typing import Optional\n\nfrom fastapi import FastAPI, HTTPException, Query, Request\nfrom fastapi.middleware.cors import CORSMiddleware\n\nfrom .agentic_assignment_engine import assign_task_agentic\nfrom .analytics_engine import build_analytics_summary\nfrom .assignment_engine import assign_single_task, assign_tasks\nfrom .database import (\n    append_assignment_log,\n    get_db_status,\n    load_assignment_logs,\n    load_history,\n    load_resources,\n    load_tasks,\n    save_resources,\n)\nfrom .event_logger import clear_events, get_events, log_event, seed_startup_events\nfrom .llm_provider import get_llm_status\nfrom .ml_ranking_model import (\n    append_candidate_training_rows,\n    assign_task_ml,\n    get_ml_status,\n    train_ml_model,\n)\nfrom .mock_generator import generate_mock_resource, generate_mock_task\nfrom .schemas import AssignmentRequest, ResourceIn, TaskIn\n\n\napp = FastAPI(\n    title="AI Task Allocation System",\n    description="Smart workforce task allocation using deterministic scoring, Agentic RAG, workflow traces, assignment history, selectable ML models, analytics, SQLite persistence, multi-provider LLM support, and live terminal telemetry.",\n    version="1.9.0",\n)\n\napp.add_middleware(\n    CORSMiddleware,\n    allow_origins=["*"],\n    allow_credentials=True,\n    allow_methods=["*"],\n    allow_headers=["*"],\n)\n\nseed_startup_events()\n\n\n@app.middleware("http")\nasync def terminal_event_middleware(request: Request, call_next):\n    started = time.perf_counter()\n\n    try:\n        response = await call_next(request)\n    except Exception as exc:\n        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)\n        log_event(\n            "api",\n            f"{request.method} {request.url.path} failed",\n            "error",\n            {\n                "path": request.url.path,\n                "method": request.method,\n                "elapsed_ms": elapsed_ms,\n                "error": str(exc),\n            },\n        )\n        raise\n\n    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)\n\n    # Avoid flooding the terminal with its own polling requests.\n    if request.url.path not in {"/system/events"}:\n        level = "success" if response.status_code < 400 else "warning"\n        log_event(\n            "api",\n            f"{request.method} {request.url.path} -> {response.status_code}",\n            level,\n            {\n                "path": request.url.path,\n                "method": request.method,\n                "status_code": response.status_code,\n                "elapsed_ms": elapsed_ms,\n            },\n        )\n\n    return response\n\n\n@app.on_event("startup")\ndef on_startup():\n    try:\n        db_status = get_db_status()\n        ml_status = get_ml_status()\n        llm_status = get_llm_status()\n\n        log_event(\n            "startup",\n            "Backend startup checks completed.",\n            "success",\n            {\n                "database": db_status.get("storage"),\n                "db_exists": db_status.get("database_exists"),\n                "ml_model_exists": ml_status.get("model_exists"),\n                "llm_provider": llm_status.get("default_provider"),\n                "ollama_running": llm_status.get("providers", {}).get("ollama", {}).get("running"),\n            },\n        )\n    except Exception as exc:\n        log_event("startup", "Startup check failed.", "error", {"error": str(exc)})\n\n\ndef _next_resource_id(resources):\n    used_numbers = []\n    for resource in resources:\n        rid = str(resource.get("resource_id", "")).upper().replace("R", "")\n        if rid.isdigit():\n            used_numbers.append(int(rid))\n    return f"R{max(used_numbers, default=0) + 1}"\n\n\ndef _log_result(result):\n    append_assignment_log(result)\n    append_candidate_training_rows(result)\n\n\n@app.get("/")\ndef health_check():\n    log_event("health", "Root health check requested.", "success")\n    return {\n        "status": "ok",\n        "app": "AI Task Allocation System",\n        "message": "Backend is running. Open /docs for API testing.",\n    }\n\n\n@app.get("/system/events")\ndef system_events(limit: int = Query(default=150, ge=1, le=700)):\n    return {\n        "events": get_events(limit=limit),\n        "count": len(get_events(limit=limit)),\n    }\n\n\n@app.delete("/system/events")\ndef delete_system_events():\n    clear_events()\n    return {\n        "message": "Terminal events cleared.",\n        "events": get_events(),\n    }\n\n\n@app.get("/system/health")\ndef system_health():\n    db_status = get_db_status()\n    ml_status = get_ml_status()\n    llm_status = get_llm_status()\n\n    log_event(\n        "system",\n        "System health snapshot generated.",\n        "success",\n        {\n            "db": db_status.get("storage"),\n            "ml_ready": ml_status.get("model_exists"),\n            "llm_provider": llm_status.get("default_provider"),\n        },\n    )\n\n    return {\n        "backend": "ok",\n        "database": db_status,\n        "ml": ml_status,\n        "llm": llm_status,\n        "event_count": len(get_events()),\n    }\n\n\n@app.get("/db/status")\ndef db_status():\n    status = get_db_status()\n    log_event(\n        "database",\n        "SQLite database status checked.",\n        "success",\n        {\n            "database_exists": status.get("database_exists"),\n            "tables": status.get("tables"),\n        },\n    )\n    return status\n\n\n@app.get("/llm/status")\ndef llm_status():\n    status = get_llm_status()\n    log_event(\n        "llm",\n        "LLM provider status checked.",\n        "success",\n        {\n            "provider": status.get("default_provider"),\n            "ollama_running": status.get("providers", {}).get("ollama", {}).get("running"),\n            "ollama_model": status.get("providers", {}).get("ollama", {}).get("model"),\n        },\n    )\n    return status\n\n\n@app.post("/mock/task")\ndef mock_task(provider: Optional[str] = Query(default=None)):\n    result = generate_mock_task(provider=provider)\n    log_event(\n        "llm",\n        "Mock task generated.",\n        "success" if result.get("llm_used") else "warning",\n        {\n            "provider": result.get("source_provider"),\n            "llm_used": result.get("llm_used"),\n            "title": result.get("title"),\n            "category": result.get("category"),\n            "fallback_reason": result.get("fallback_reason"),\n        },\n    )\n    return result\n\n\n@app.post("/mock/resource")\ndef mock_resource(provider: Optional[str] = Query(default=None)):\n    result = generate_mock_resource(provider=provider)\n    log_event(\n        "llm",\n        "Mock resource generated.",\n        "success" if result.get("llm_used") else "warning",\n        {\n            "provider": result.get("source_provider"),\n            "llm_used": result.get("llm_used"),\n            "name": result.get("name"),\n            "skills": result.get("skills"),\n            "fallback_reason": result.get("fallback_reason"),\n        },\n    )\n    return result\n\n\n@app.get("/analytics/summary")\ndef analytics_summary(limit: int = Query(default=500, ge=1, le=2000)):\n    summary = build_analytics_summary(limit=limit)\n    log_event(\n        "analytics",\n        "Analytics dashboard data loaded.",\n        "success",\n        {\n            "assignments": summary.get("summary", {}).get("total_assignments"),\n            "resources": summary.get("summary", {}).get("total_resources"),\n            "ml_ready": summary.get("summary", {}).get("ml_model_ready"),\n        },\n    )\n    return summary\n\n\n@app.get("/resources")\ndef get_resources():\n    resources = load_resources()\n    log_event(\n        "resources",\n        "Resources loaded.",\n        "success",\n        {"count": len(resources)},\n    )\n    return resources\n\n\n@app.post("/resources")\ndef create_resource(resource: ResourceIn):\n    resources = load_resources()\n    data = resource.model_dump()\n\n    if not data["resource_id"]:\n        data["resource_id"] = _next_resource_id(resources)\n\n    if any(item["resource_id"] == data["resource_id"] for item in resources):\n        log_event(\n            "resources",\n            "Resource creation blocked because ID already exists.",\n            "error",\n            {"resource_id": data["resource_id"]},\n        )\n        raise HTTPException(status_code=409, detail="Resource ID already exists.")\n\n    data["skills"] = [skill.strip().lower() for skill in data["skills"] if skill.strip()]\n    data["handled_categories"] = [\n        category.strip().lower()\n        for category in data["handled_categories"]\n        if category.strip()\n    ]\n    data["status"] = data["status"].lower()\n\n    resources.append(data)\n    save_resources(resources)\n\n    log_event(\n        "resources",\n        f"Resource added: {data.get(\'name\')}",\n        "success",\n        {\n            "resource_id": data.get("resource_id"),\n            "name": data.get("name"),\n            "status": data.get("status"),\n            "skills": data.get("skills"),\n        },\n    )\n\n    return {\n        "message": "Resource created successfully.",\n        "resource": data,\n    }\n\n\n@app.put("/resources/{resource_id}")\ndef update_resource(resource_id: str, resource: ResourceIn):\n    resources = load_resources()\n    data = resource.model_dump()\n    data["resource_id"] = resource_id\n    data["skills"] = [skill.strip().lower() for skill in data["skills"] if skill.strip()]\n    data["handled_categories"] = [\n        category.strip().lower()\n        for category in data["handled_categories"]\n        if category.strip()\n    ]\n    data["status"] = data["status"].lower()\n\n    for index, existing in enumerate(resources):\n        if existing["resource_id"] == resource_id:\n            resources[index] = data\n            save_resources(resources)\n            log_event(\n                "resources",\n                f"Resource updated: {data.get(\'name\')}",\n                "success",\n                {"resource_id": resource_id, "name": data.get("name")},\n            )\n            return {\n                "message": "Resource updated successfully.",\n                "resource": data,\n            }\n\n    log_event("resources", "Resource update failed: resource not found.", "error", {"resource_id": resource_id})\n    raise HTTPException(status_code=404, detail="Resource not found.")\n\n\n@app.delete("/resources/{resource_id}")\ndef delete_resource(resource_id: str):\n    resources = load_resources()\n    remaining = [resource for resource in resources if resource["resource_id"] != resource_id]\n\n    if len(remaining) == len(resources):\n        log_event("resources", "Resource deletion failed: resource not found.", "error", {"resource_id": resource_id})\n        raise HTTPException(status_code=404, detail="Resource not found.")\n\n    save_resources(remaining)\n    log_event("resources", "Resource deleted.", "warning", {"resource_id": resource_id})\n\n    return {\n        "message": "Resource deleted successfully.",\n        "resource_id": resource_id,\n    }\n\n\n@app.get("/tasks")\ndef get_tasks():\n    tasks = load_tasks()\n    log_event("tasks", "Sample tasks loaded.", "success", {"count": len(tasks)})\n    return tasks\n\n\n@app.get("/history")\ndef get_history():\n    history = load_history()\n    log_event("history", "Task history loaded.", "success", {"count": len(history)})\n    return history\n\n\n@app.get("/assignment-logs")\ndef get_assignment_logs(limit: int = Query(default=50, ge=1, le=500)):\n    logs = load_assignment_logs(limit=limit)\n    log_event("history", "Assignment logs loaded.", "success", {"count": len(logs)})\n    return logs\n\n\n@app.get("/ml/status")\ndef ml_status():\n    status = get_ml_status()\n    log_event(\n        "ml",\n        "ML status checked.",\n        "success",\n        {\n            "model_exists": status.get("model_exists"),\n            "model_type": status.get("metadata", {}).get("model_type"),\n            "training_rows": status.get("training_rows"),\n            "query_groups": status.get("query_groups"),\n        },\n    )\n    return status\n\n\n@app.post("/ml/train")\ndef ml_train(model_type: Optional[str] = Query(default="lightgbm_ranker")):\n    log_event("ml", f"Training requested for model strategy: {model_type}", "info", {"model_type": model_type})\n    result = train_ml_model(model_type=model_type)\n\n    log_event(\n        "ml",\n        result.get("message", "ML training finished."),\n        "success" if result.get("trained") else "warning",\n        {\n            "trained": result.get("trained"),\n            "model_type": result.get("metadata", {}).get("model_type"),\n            "hit_at_1": result.get("metadata", {}).get("train_hit_at_1"),\n            "training_rows": result.get("metadata", {}).get("training_rows"),\n        },\n    )\n\n    return result\n\n\n@app.post("/assign")\ndef assign_task(task: TaskIn, now_hhmm: Optional[str] = Query(default=None)):\n    log_event(\n        "assignment",\n        "Normal assignment started.",\n        "info",\n        {"task": task.title, "priority": task.priority, "category": task.category, "time": now_hhmm},\n    )\n\n    result = assign_single_task(task.model_dump(), now_hhmm=now_hhmm)\n    _log_result(result)\n\n    log_event(\n        "assignment",\n        "Normal assignment completed.",\n        "success" if result.get("assigned") else "warning",\n        {\n            "assigned": result.get("assigned"),\n            "resource": (result.get("assigned_resource") or {}).get("name"),\n            "score": (result.get("assigned_resource") or {}).get("score"),\n            "candidates": len(result.get("candidates", [])),\n        },\n    )\n\n    return result\n\n\n@app.post("/assign/agentic")\ndef assign_task_with_agentic_rag(task: TaskIn, now_hhmm: Optional[str] = Query(default=None)):\n    log_event(\n        "assignment",\n        "Agentic RAG assignment started.",\n        "info",\n        {"task": task.title, "priority": task.priority, "category": task.category, "time": now_hhmm},\n    )\n\n    result = assign_task_agentic(task.model_dump(), now_hhmm=now_hhmm)\n    _log_result(result)\n\n    log_event(\n        "rag",\n        "Agentic RAG assignment completed.",\n        "success" if result.get("assigned") else "warning",\n        {\n            "assigned": result.get("assigned"),\n            "resource": (result.get("assigned_resource") or {}).get("name"),\n            "similar_cases": len(result.get("rag_context", {}).get("similar_cases", [])),\n            "policy_chunks": len(result.get("rag_context", {}).get("policy_context", [])),\n            "workflow_steps": len(result.get("workflow_trace", [])),\n        },\n    )\n\n    return result\n\n\n@app.post("/assign/ml")\ndef assign_task_with_ml_ranker(\n    task: TaskIn,\n    now_hhmm: Optional[str] = Query(default=None),\n    model_type: Optional[str] = Query(default=None),\n):\n    log_event(\n        "assignment",\n        "ML assignment started.",\n        "info",\n        {\n            "task": task.title,\n            "priority": task.priority,\n            "category": task.category,\n            "time": now_hhmm,\n            "requested_model_type": model_type,\n        },\n    )\n\n    result = assign_task_ml(task.model_dump(), now_hhmm=now_hhmm, model_type=model_type)\n    _log_result(result)\n\n    log_event(\n        "ml",\n        "ML assignment completed.",\n        "success" if result.get("assigned") else "warning",\n        {\n            "assigned": result.get("assigned"),\n            "resource": (result.get("assigned_resource") or {}).get("name"),\n            "score": (result.get("assigned_resource") or {}).get("score"),\n            "model_type": (result.get("assigned_resource") or {}).get("model_type"),\n            "warning": result.get("model_warning"),\n        },\n    )\n\n    return result\n\n\n@app.post("/assign/batch")\ndef assign_batch(payload: AssignmentRequest):\n    log_event("assignment", "Batch assignment started.", "info", {"task_count": len(payload.tasks), "time": payload.now_hhmm})\n\n    result = assign_tasks(\n        [task.model_dump() for task in payload.tasks],\n        now_hhmm=payload.now_hhmm,\n    )\n\n    for item in result.get("assignments", []):\n        _log_result(item)\n\n    log_event(\n        "assignment",\n        "Batch assignment completed.",\n        "success",\n        {\n            "total_tasks": result.get("total_tasks"),\n            "assigned_count": result.get("assigned_count"),\n            "unassigned_count": result.get("unassigned_count"),\n        },\n    )\n\n    return result\n\n\n@app.post("/assign/sample")\ndef assign_sample(now_hhmm: Optional[str] = Query(default="10:30")):\n    tasks = load_tasks()\n    log_event("assignment", "Sample batch assignment started.", "info", {"task_count": len(tasks), "time": now_hhmm})\n\n    result = assign_tasks(tasks, now_hhmm=now_hhmm)\n\n    for item in result.get("assignments", []):\n        _log_result(item)\n\n    log_event(\n        "assignment",\n        "Sample batch assignment completed.",\n        "success",\n        {\n            "total_tasks": result.get("total_tasks"),\n            "assigned_count": result.get("assigned_count"),\n            "unassigned_count": result.get("unassigned_count"),\n        },\n    )\n\n    return result\n',
    'frontend/src/components/TerminalPanel.jsx': '\nimport { useEffect, useRef, useState } from "react";\n\nimport { apiDelete, apiGet } from "../api/client";\n\nfunction formatTime(timestamp) {\n  if (!timestamp) return "";\n  return timestamp.replace("T", " ");\n}\n\nfunction EventLine({ event }) {\n  return (\n    <div className={`terminalLine ${event.level}`}>\n      <span className="terminalTime">{formatTime(event.timestamp)}</span>\n      <span className="terminalLevel">{event.level}</span>\n      <span className="terminalSource">{event.source}</span>\n      <span className="terminalMessage">{event.message}</span>\n      {event.data && Object.keys(event.data).length > 0 && (\n        <pre>{JSON.stringify(event.data, null, 2)}</pre>\n      )}\n    </div>\n  );\n}\n\nexport default function TerminalPanel() {\n  const [events, setEvents] = useState([]);\n  const [health, setHealth] = useState(null);\n  const [expanded, setExpanded] = useState(true);\n  const [autoScroll, setAutoScroll] = useState(true);\n  const [error, setError] = useState("");\n  const terminalRef = useRef(null);\n\n  async function loadEvents() {\n    try {\n      const data = await apiGet("/system/events?limit=180");\n      setEvents(data.events || []);\n      setError("");\n    } catch (err) {\n      setError(err.message);\n    }\n  }\n\n  async function loadHealth() {\n    try {\n      const data = await apiGet("/system/health");\n      setHealth(data);\n    } catch (err) {\n      setError(err.message);\n    }\n  }\n\n  async function clearTerminal() {\n    try {\n      const data = await apiDelete("/system/events");\n      setEvents(data.events || []);\n    } catch (err) {\n      setError(err.message);\n    }\n  }\n\n  useEffect(() => {\n    loadEvents();\n    loadHealth();\n\n    const eventsInterval = setInterval(loadEvents, 1500);\n    const healthInterval = setInterval(loadHealth, 5000);\n\n    return () => {\n      clearInterval(eventsInterval);\n      clearInterval(healthInterval);\n    };\n  }, []);\n\n  useEffect(() => {\n    if (!autoScroll || !terminalRef.current) return;\n    terminalRef.current.scrollTop = terminalRef.current.scrollHeight;\n  }, [events, autoScroll, expanded]);\n\n  const dbReady = health?.database?.database_exists;\n  const mlReady = health?.ml?.model_exists;\n  const ollamaReady = health?.llm?.providers?.ollama?.running;\n  const modelType = health?.ml?.metadata?.model_type || "not trained";\n\n  return (\n    <div className="terminalCard">\n      <div className="terminalHeader">\n        <div>\n          <h2>Backend Terminal Monitor</h2>\n          <p>\n            Live event stream for API calls, health checks, model training, assignments,\n            RAG retrieval, LLM mock generation, SQLite, and resource updates.\n          </p>\n        </div>\n\n        <div className="terminalControls">\n          <button type="button" onClick={() => setExpanded((value) => !value)}>\n            {expanded ? "Collapse" : "Expand"}\n          </button>\n          <button type="button" onClick={() => setAutoScroll((value) => !value)}>\n            Auto-scroll {autoScroll ? "On" : "Off"}\n          </button>\n          <button type="button" onClick={clearTerminal}>\n            Clear\n          </button>\n        </div>\n      </div>\n\n      <div className="terminalStatusGrid">\n        <div className={dbReady ? "ok" : "bad"}>\n          <b>SQLite</b>\n          <span>{dbReady ? "online" : "offline"}</span>\n        </div>\n        <div className={mlReady ? "ok" : "warn"}>\n          <b>ML Model</b>\n          <span>{mlReady ? modelType : "not trained"}</span>\n        </div>\n        <div className={ollamaReady ? "ok" : "warn"}>\n          <b>Ollama</b>\n          <span>{ollamaReady ? health?.llm?.providers?.ollama?.model : "offline"}</span>\n        </div>\n        <div className="ok">\n          <b>Events</b>\n          <span>{events.length}</span>\n        </div>\n      </div>\n\n      {error && <div className="terminalError">{error}</div>}\n\n      {expanded && (\n        <div className="terminalWindow" ref={terminalRef}>\n          {events.length === 0 ? (\n            <div className="terminalEmpty">No backend events yet.</div>\n          ) : (\n            events.map((event) => <EventLine key={event.id} event={event} />)\n          )}\n        </div>\n      )}\n    </div>\n  );\n}\n',
    'frontend/src/App.jsx': '\nimport { useEffect, useState } from "react";\n\nimport { apiDelete, apiGet, apiPost } from "./api/client";\nimport AssignmentCard from "./components/AssignmentCard";\nimport AssignmentHistory from "./components/AssignmentHistory";\nimport Dashboard from "./components/Dashboard";\nimport LLMPanel from "./components/LLMPanel";\nimport MLPanel from "./components/MLPanel";\nimport ResourceForm from "./components/ResourceForm";\nimport ResourceTable from "./components/ResourceTable";\nimport TaskForm from "./components/TaskForm";\nimport TaskTable from "./components/TaskTable";\nimport TerminalPanel from "./components/TerminalPanel";\n\nfunction SingleAssignmentResult({ result }) {\n  if (!result) return null;\n\n  const title =\n    result.mode === "agentic_rag"\n      ? "Agentic RAG Assignment Result"\n      : result.mode === "ml_ranker" || result.mode === "ml_ranker_fallback"\n        ? "ML Strategy Assignment Result"\n        : "Custom Task Assignment Result";\n\n  return (\n    <div className="card">\n      <h2>{title}</h2>\n      <AssignmentCard item={result} />\n    </div>\n  );\n}\n\nfunction BatchAssignmentResult({ result }) {\n  if (!result) return null;\n\n  return (\n    <div className="card">\n      <h2>Sample Batch Assignment Result</h2>\n      <p>\n        Assigned {result.assigned_count} of {result.total_tasks} tasks.\n        Unassigned: {result.unassigned_count}.\n      </p>\n\n      <div className="results">\n        {result.assignments.map((item) => (\n          <AssignmentCard key={item.task.task_id} item={item} />\n        ))}\n      </div>\n    </div>\n  );\n}\n\nexport default function App() {\n  const [resources, setResources] = useState([]);\n  const [tasks, setTasks] = useState([]);\n  const [assignmentLogs, setAssignmentLogs] = useState([]);\n  const [mlStatus, setMlStatus] = useState(null);\n  const [llmStatus, setLlmStatus] = useState(null);\n  const [analytics, setAnalytics] = useState(null);\n  const [selectedModelType, setSelectedModelType] = useState("lightgbm_ranker");\n  const [batchResult, setBatchResult] = useState(null);\n  const [singleResult, setSingleResult] = useState(null);\n  const [now, setNow] = useState("10:30");\n  const [loadingBatch, setLoadingBatch] = useState(false);\n  const [loadingSingle, setLoadingSingle] = useState(false);\n  const [loadingAgentic, setLoadingAgentic] = useState(false);\n  const [loadingMl, setLoadingMl] = useState(false);\n  const [loadingTrain, setLoadingTrain] = useState(false);\n  const [loadingResource, setLoadingResource] = useState(false);\n  const [loadingMockTask, setLoadingMockTask] = useState(false);\n  const [loadingMockResource, setLoadingMockResource] = useState(false);\n  const [error, setError] = useState("");\n\n  async function loadData() {\n    try {\n      const [resourceData, taskData, logsData, mlData, analyticsData, llmData] = await Promise.all([\n        apiGet("/resources"),\n        apiGet("/tasks"),\n        apiGet("/assignment-logs"),\n        apiGet("/ml/status"),\n        apiGet("/analytics/summary"),\n        apiGet("/llm/status"),\n      ]);\n\n      setResources(resourceData);\n      setTasks(taskData);\n      setAssignmentLogs(logsData);\n      setMlStatus(mlData);\n      setAnalytics(analyticsData);\n      setLlmStatus(llmData);\n\n      const trainedType = mlData?.metadata?.requested_model_type;\n      if (trainedType) {\n        setSelectedModelType(trainedType);\n      }\n    } catch (err) {\n      setError(err.message);\n    }\n  }\n\n  async function refreshRuntimeData() {\n    try {\n      const [logsData, mlData, analyticsData, llmData] = await Promise.all([\n        apiGet("/assignment-logs"),\n        apiGet("/ml/status"),\n        apiGet("/analytics/summary"),\n        apiGet("/llm/status"),\n      ]);\n      setAssignmentLogs(logsData);\n      setMlStatus(mlData);\n      setAnalytics(analyticsData);\n      setLlmStatus(llmData);\n    } catch (err) {\n      setError(err.message);\n    }\n  }\n\n  async function generateMockTask() {\n    setLoadingMockTask(true);\n    setError("");\n\n    try {\n      const data = await apiPost("/mock/task?provider=ollama");\n      if (!data.llm_used && data.fallback_reason) {\n        setError(`Mock task used fallback: ${data.fallback_reason}`);\n      }\n      return data;\n    } catch (err) {\n      setError(err.message);\n      return null;\n    } finally {\n      setLoadingMockTask(false);\n    }\n  }\n\n  async function generateMockResource() {\n    setLoadingMockResource(true);\n    setError("");\n\n    try {\n      const data = await apiPost("/mock/resource?provider=ollama");\n      if (!data.llm_used && data.fallback_reason) {\n        setError(`Mock resource used fallback: ${data.fallback_reason}`);\n      }\n      return data;\n    } catch (err) {\n      setError(err.message);\n      return null;\n    } finally {\n      setLoadingMockResource(false);\n    }\n  }\n\n  async function trainMlRanker(modelType) {\n    setLoadingTrain(true);\n    setError("");\n\n    try {\n      const data = await apiPost(`/ml/train?model_type=${encodeURIComponent(modelType)}`);\n      setMlStatus(data.status || data);\n      await refreshRuntimeData();\n      if (!data.trained) {\n        setError(data.message);\n      }\n    } catch (err) {\n      setError(err.message);\n    } finally {\n      setLoadingTrain(false);\n    }\n  }\n\n  async function createResource(payload) {\n    setLoadingResource(true);\n    setError("");\n\n    try {\n      await apiPost("/resources", payload);\n      await loadData();\n    } catch (err) {\n      setError(err.message);\n    } finally {\n      setLoadingResource(false);\n    }\n  }\n\n  async function deleteResource(resourceId) {\n    const confirmed = window.confirm("Delete this resource?");\n    if (!confirmed) return;\n\n    setError("");\n\n    try {\n      await apiDelete(`/resources/${resourceId}`);\n      await loadData();\n    } catch (err) {\n      setError(err.message);\n    }\n  }\n\n  async function runSampleAssignment() {\n    setLoadingBatch(true);\n    setError("");\n\n    try {\n      const data = await apiPost(`/assign/sample?now_hhmm=${encodeURIComponent(now)}`);\n      setBatchResult(data);\n      await refreshRuntimeData();\n    } catch (err) {\n      setError(err.message);\n    } finally {\n      setLoadingBatch(false);\n    }\n  }\n\n  async function runCustomAssignment(taskPayload) {\n    setLoadingSingle(true);\n    setError("");\n\n    try {\n      const data = await apiPost(`/assign?now_hhmm=${encodeURIComponent(now)}`, taskPayload);\n      setSingleResult(data);\n      await refreshRuntimeData();\n    } catch (err) {\n      setError(err.message);\n    } finally {\n      setLoadingSingle(false);\n    }\n  }\n\n  async function runAgenticAssignment(taskPayload) {\n    setLoadingAgentic(true);\n    setError("");\n\n    try {\n      const data = await apiPost(`/assign/agentic?now_hhmm=${encodeURIComponent(now)}`, taskPayload);\n      setSingleResult(data);\n      await refreshRuntimeData();\n    } catch (err) {\n      setError(err.message);\n    } finally {\n      setLoadingAgentic(false);\n    }\n  }\n\n  async function runMlAssignment(taskPayload, modelType) {\n    setLoadingMl(true);\n    setError("");\n\n    try {\n      const data = await apiPost(\n        `/assign/ml?now_hhmm=${encodeURIComponent(now)}&model_type=${encodeURIComponent(modelType)}`,\n        taskPayload\n      );\n      setSingleResult(data);\n      await refreshRuntimeData();\n    } catch (err) {\n      setError(err.message);\n    } finally {\n      setLoadingMl(false);\n    }\n  }\n\n  useEffect(() => {\n    loadData();\n  }, []);\n\n  return (\n    <main className="app">\n      <section className="hero">\n        <div>\n          <h1>AI Task Allocation System</h1>\n          <p>\n            Assign service/support tasks using deterministic scoring, Agentic RAG retrieval,\n            workflow traces, assignment history, selectable ML models, SQLite, analytics,\n            live backend telemetry, and optional LLM providers.\n          </p>\n        </div>\n\n        <div className="controls">\n          <label>\n            Demo time{" "}\n            <input value={now} onChange={(event) => setNow(event.target.value)} />\n          </label>\n          <button onClick={runSampleAssignment} disabled={loadingBatch}>\n            {loadingBatch ? "Assigning..." : "Run Sample Batch"}\n          </button>\n        </div>\n      </section>\n\n      {error && <div className="error">{error}</div>}\n\n      <section className="grid">\n        <TerminalPanel />\n\n        <Dashboard analytics={analytics} />\n        <LLMPanel status={llmStatus} />\n\n        <TaskForm\n          onAssign={runCustomAssignment}\n          onAgenticAssign={runAgenticAssignment}\n          onMlAssign={runMlAssignment}\n          onGenerateMockTask={generateMockTask}\n          selectedModelType={selectedModelType}\n          loading={loadingSingle}\n          agenticLoading={loadingAgentic}\n          mlLoading={loadingMl}\n          mockTaskLoading={loadingMockTask}\n        />\n\n        <SingleAssignmentResult result={singleResult} />\n\n        <MLPanel\n          status={mlStatus}\n          selectedModelType={selectedModelType}\n          onModelTypeChange={setSelectedModelType}\n          onTrain={trainMlRanker}\n          loading={loadingTrain}\n        />\n\n        <AssignmentHistory logs={assignmentLogs} />\n\n        <ResourceForm\n          onCreate={createResource}\n          onGenerateMockResource={generateMockResource}\n          loading={loadingResource}\n          mockResourceLoading={loadingMockResource}\n        />\n        <ResourceTable resources={resources} onDelete={deleteResource} />\n\n        <TaskTable tasks={tasks} />\n\n        <BatchAssignmentResult result={batchResult} />\n      </section>\n    </main>\n  );\n}\n',
}

for path, content in FILES.items():
    write_file(path, content)

css_path = ROOT / 'frontend/src/styles.css'
extra_css = '''

.terminalCard {
  border: 1px solid #1f3b57;
  border-radius: 18px;
  background: #050b14;
  padding: 16px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.28);
}

.terminalHeader {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: start;
  margin-bottom: 12px;
}

.terminalHeader h2 {
  margin: 0 0 5px;
  color: #dbeafe;
}

.terminalHeader p {
  margin: 0;
  color: #9ca3af;
}

.terminalControls {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.terminalControls button {
  padding: 8px 10px;
  border-radius: 10px;
  background: #0f172a;
  color: #dbeafe;
  border: 1px solid #334155;
}

.terminalStatusGrid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
  margin-bottom: 12px;
}

.terminalStatusGrid div {
  border: 1px solid #263244;
  border-radius: 12px;
  background: #0f172a;
  padding: 10px;
}

.terminalStatusGrid b,
.terminalStatusGrid span {
  display: block;
}

.terminalStatusGrid b {
  color: #93c5fd;
}

.terminalStatusGrid span {
  margin-top: 4px;
  color: #e5e7eb;
}

.terminalStatusGrid .ok {
  border-color: #065f46;
}

.terminalStatusGrid .warn {
  border-color: #92400e;
}

.terminalStatusGrid .bad {
  border-color: #991b1b;
}

.terminalWindow {
  height: 360px;
  overflow: auto;
  border: 1px solid #1f2937;
  border-radius: 14px;
  background: #020617;
  padding: 12px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}

.terminalLine {
  display: grid;
  grid-template-columns: 150px 78px 110px 1fr;
  gap: 10px;
  align-items: start;
  border-bottom: 1px solid rgba(148, 163, 184, 0.12);
  padding: 8px 0;
  color: #cbd5e1;
}

.terminalLine pre {
  grid-column: 4 / 5;
  white-space: pre-wrap;
  margin: 4px 0 0;
  color: #94a3b8;
}

.terminalTime { color: #64748b; }
.terminalSource { color: #a78bfa; font-weight: 800; }
.terminalMessage { color: #e5e7eb; }

.terminalLevel {
  border-radius: 999px;
  padding: 2px 7px;
  text-align: center;
  text-transform: uppercase;
  font-size: 11px;
  font-weight: 900;
  background: #334155;
  color: #e5e7eb;
}

.terminalLine.success .terminalLevel { background: #065f46; color: #a7f3d0; }
.terminalLine.warning .terminalLevel { background: #92400e; color: #fde68a; }
.terminalLine.error .terminalLevel { background: #991b1b; color: #fecaca; }
.terminalLine.info .terminalLevel { background: #1e3a8a; color: #bfdbfe; }

.terminalError {
  border-radius: 12px;
  padding: 10px;
  margin-bottom: 10px;
  background: #7f1d1d;
  color: #fecaca;
}

.terminalEmpty {
  color: #64748b;
  padding: 20px;
}

@media (max-width: 900px) {
  .terminalHeader { flex-direction: column; }
  .terminalStatusGrid { grid-template-columns: 1fr; }
  .terminalLine { grid-template-columns: 1fr; }
  .terminalLine pre { grid-column: auto; }
}
'''
if css_path.exists():
    current = css_path.read_text(encoding='utf-8')
    if '.terminalCard' not in current:
        css_path.write_text(current.rstrip() + extra_css + '\n', encoding='utf-8')
        print('updated: frontend/src/styles.css')

readme = ROOT / 'README.md'
section = '''

## Backend Terminal Monitor

The frontend now includes a live terminal-style monitor at the top of the dashboard.

New endpoints:

```txt
GET    /system/events
GET    /system/health
DELETE /system/events
```

It shows events for:

```txt
API calls
SQLite health
LLM/Ollama status
mock task/resource generation
resource add/update/delete
normal assignment
Agentic RAG assignment
ML assignment
ML strategy training
analytics loading
assignment history loading
```

This makes the full backend workflow visible during demos.
'''
if readme.exists():
    current = readme.read_text(encoding='utf-8')
    if '## Backend Terminal Monitor' not in current:
        readme.write_text(current.rstrip() + section + '\n', encoding='utf-8')
        print('updated: README.md')

print('\nBackend terminal monitor upgrade added successfully.')
print('Next: restart backend, refresh frontend, then watch the terminal while using the app.')