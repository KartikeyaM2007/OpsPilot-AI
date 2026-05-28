import time
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware

from .agentic_assignment_engine import assign_task_agentic
from .analytics_engine import build_analytics_summary
from .assignment_engine import assign_single_task, assign_tasks
from .database import (
    append_assignment_log,
    get_db_status,
    load_assignment_logs,
    load_history,
    load_resources,
    load_tasks,
    save_resources,
)
from .event_logger import clear_events, get_events, log_event, seed_startup_events
from .llm_provider import get_llm_status
from .ml_ranking_model import (
    append_candidate_training_rows,
    assign_task_ml,
    get_ml_status,
    train_ml_model,
)
from .mock_generator import generate_mock_resource, generate_mock_task
from .schemas import AssignmentRequest, ResourceIn, TaskIn


app = FastAPI(
    title="AI Task Allocation System",
    description="Smart workforce task allocation using deterministic scoring, Agentic RAG, workflow traces, assignment history, selectable ML models, analytics, SQLite persistence, multi-provider LLM support, and live terminal telemetry.",
    version="1.9.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

seed_startup_events()


@app.middleware("http")
async def terminal_event_middleware(request: Request, call_next):
    started = time.perf_counter()

    try:
        response = await call_next(request)
    except Exception as exc:
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        log_event(
            "api",
            f"{request.method} {request.url.path} failed",
            "error",
            {
                "path": request.url.path,
                "method": request.method,
                "elapsed_ms": elapsed_ms,
                "error": str(exc),
            },
        )
        raise

    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)

    # Avoid flooding the terminal with its own polling requests.
    if request.url.path not in {"/system/events", "/system/health"}:
        level = "success" if response.status_code < 400 else "warning"
        log_event(
            "api",
            f"{request.method} {request.url.path} -> {response.status_code}",
            level,
            {
                "path": request.url.path,
                "method": request.method,
                "status_code": response.status_code,
                "elapsed_ms": elapsed_ms,
            },
        )

    return response


@app.on_event("startup")
def on_startup():
    try:
        db_status = get_db_status()
        ml_status = get_ml_status()
        llm_status = get_llm_status()

        log_event(
            "startup",
            "Backend startup checks completed.",
            "success",
            {
                "database": db_status.get("storage"),
                "db_exists": db_status.get("database_exists"),
                "ml_model_exists": ml_status.get("model_exists"),
                "llm_provider": llm_status.get("default_provider"),
                "ollama_running": llm_status.get("providers", {}).get("ollama", {}).get("running"),
            },
        )
    except Exception as exc:
        log_event("startup", "Startup check failed.", "error", {"error": str(exc)})


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
    log_event("health", "Root health check requested.", "success")
    return {
        "status": "ok",
        "app": "AI Task Allocation System",
        "message": "Backend is running. Open /docs for API testing.",
    }


@app.get("/system/events")
def system_events(limit: int = Query(default=150, ge=1, le=700)):
    return {
        "events": get_events(limit=limit),
        "count": len(get_events(limit=limit)),
    }


@app.delete("/system/events")
def delete_system_events():
    clear_events()
    return {
        "message": "Terminal events cleared.",
        "events": get_events(),
    }


@app.get("/system/health")
def system_health():
    # Silent snapshot endpoint used by the frontend terminal header.
    # It should not create log events, otherwise the terminal fills itself forever.
    db_status = get_db_status()
    ml_status = get_ml_status()
    llm_status = get_llm_status()

    return {
        "backend": "ok",
        "database": db_status,
        "ml": ml_status,
        "llm": llm_status,
        "event_count": len(get_events()),
    }


@app.get("/db/status")
def db_status():
    status = get_db_status()
    log_event(
        "database",
        "SQLite database status checked.",
        "success",
        {
            "database_exists": status.get("database_exists"),
            "tables": status.get("tables"),
        },
    )
    return status


@app.get("/llm/status")
def llm_status():
    status = get_llm_status()
    log_event(
        "llm",
        "LLM provider status checked.",
        "success",
        {
            "provider": status.get("default_provider"),
            "ollama_running": status.get("providers", {}).get("ollama", {}).get("running"),
            "ollama_model": status.get("providers", {}).get("ollama", {}).get("model"),
        },
    )
    return status


@app.post("/mock/task")
def mock_task(provider: Optional[str] = Query(default=None)):
    result = generate_mock_task(provider=provider)
    log_event(
        "llm",
        "Mock task generated.",
        "success" if result.get("llm_used") else "warning",
        {
            "provider": result.get("source_provider"),
            "llm_used": result.get("llm_used"),
            "title": result.get("title"),
            "category": result.get("category"),
            "fallback_reason": result.get("fallback_reason"),
        },
    )
    return result


@app.post("/mock/resource")
def mock_resource(provider: Optional[str] = Query(default=None)):
    result = generate_mock_resource(provider=provider)
    log_event(
        "llm",
        "Mock resource generated.",
        "success" if result.get("llm_used") else "warning",
        {
            "provider": result.get("source_provider"),
            "llm_used": result.get("llm_used"),
            "name": result.get("name"),
            "skills": result.get("skills"),
            "fallback_reason": result.get("fallback_reason"),
        },
    )
    return result


@app.get("/analytics/summary")
def analytics_summary(limit: int = Query(default=500, ge=1, le=2000)):
    summary = build_analytics_summary(limit=limit)
    log_event(
        "analytics",
        "Analytics dashboard data loaded.",
        "success",
        {
            "assignments": summary.get("summary", {}).get("total_assignments"),
            "resources": summary.get("summary", {}).get("total_resources"),
            "ml_ready": summary.get("summary", {}).get("ml_model_ready"),
        },
    )
    return summary


@app.get("/resources")
def get_resources():
    resources = load_resources()
    log_event(
        "resources",
        "Resources loaded.",
        "success",
        {"count": len(resources)},
    )
    return resources


@app.post("/resources")
def create_resource(resource: ResourceIn):
    resources = load_resources()
    data = resource.model_dump()

    if not data["resource_id"]:
        data["resource_id"] = _next_resource_id(resources)

    if any(item["resource_id"] == data["resource_id"] for item in resources):
        log_event(
            "resources",
            "Resource creation blocked because ID already exists.",
            "error",
            {"resource_id": data["resource_id"]},
        )
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

    log_event(
        "resources",
        f"Resource added: {data.get('name')}",
        "success",
        {
            "resource_id": data.get("resource_id"),
            "name": data.get("name"),
            "status": data.get("status"),
            "skills": data.get("skills"),
        },
    )

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
            log_event(
                "resources",
                f"Resource updated: {data.get('name')}",
                "success",
                {"resource_id": resource_id, "name": data.get("name")},
            )
            return {
                "message": "Resource updated successfully.",
                "resource": data,
            }

    log_event("resources", "Resource update failed: resource not found.", "error", {"resource_id": resource_id})
    raise HTTPException(status_code=404, detail="Resource not found.")


@app.delete("/resources/{resource_id}")
def delete_resource(resource_id: str):
    resources = load_resources()
    remaining = [resource for resource in resources if resource["resource_id"] != resource_id]

    if len(remaining) == len(resources):
        log_event("resources", "Resource deletion failed: resource not found.", "error", {"resource_id": resource_id})
        raise HTTPException(status_code=404, detail="Resource not found.")

    save_resources(remaining)
    log_event("resources", "Resource deleted.", "warning", {"resource_id": resource_id})

    return {
        "message": "Resource deleted successfully.",
        "resource_id": resource_id,
    }


@app.get("/tasks")
def get_tasks():
    tasks = load_tasks()
    log_event("tasks", "Sample tasks loaded.", "success", {"count": len(tasks)})
    return tasks


@app.get("/history")
def get_history():
    history = load_history()
    log_event("history", "Task history loaded.", "success", {"count": len(history)})
    return history


@app.get("/assignment-logs")
def get_assignment_logs(limit: int = Query(default=50, ge=1, le=500)):
    logs = load_assignment_logs(limit=limit)
    log_event("history", "Assignment logs loaded.", "success", {"count": len(logs)})
    return logs


@app.get("/ml/status")
def ml_status():
    status = get_ml_status()
    log_event(
        "ml",
        "ML status checked.",
        "success",
        {
            "model_exists": status.get("model_exists"),
            "model_type": status.get("metadata", {}).get("model_type"),
            "training_rows": status.get("training_rows"),
            "query_groups": status.get("query_groups"),
        },
    )
    return status


@app.post("/ml/train")
def ml_train(model_type: Optional[str] = Query(default="lightgbm_ranker")):
    log_event("ml", f"Training requested for model strategy: {model_type}", "info", {"model_type": model_type})
    result = train_ml_model(model_type=model_type)

    log_event(
        "ml",
        result.get("message", "ML training finished."),
        "success" if result.get("trained") else "warning",
        {
            "trained": result.get("trained"),
            "model_type": result.get("metadata", {}).get("model_type"),
            "hit_at_1": result.get("metadata", {}).get("train_hit_at_1"),
            "training_rows": result.get("metadata", {}).get("training_rows"),
        },
    )

    return result


@app.post("/assign")
def assign_task(task: TaskIn, now_hhmm: Optional[str] = Query(default=None)):
    log_event(
        "assignment",
        "Normal assignment started.",
        "info",
        {"task": task.title, "priority": task.priority, "category": task.category, "time": now_hhmm},
    )

    result = assign_single_task(task.model_dump(), now_hhmm=now_hhmm)
    _log_result(result)

    log_event(
        "assignment",
        "Normal assignment completed.",
        "success" if result.get("assigned") else "warning",
        {
            "assigned": result.get("assigned"),
            "resource": (result.get("assigned_resource") or {}).get("name"),
            "score": (result.get("assigned_resource") or {}).get("score"),
            "candidates": len(result.get("candidates", [])),
        },
    )

    return result


@app.post("/assign/agentic")
def assign_task_with_agentic_rag(task: TaskIn, now_hhmm: Optional[str] = Query(default=None)):
    log_event(
        "assignment",
        "Agentic RAG assignment started.",
        "info",
        {"task": task.title, "priority": task.priority, "category": task.category, "time": now_hhmm},
    )

    result = assign_task_agentic(task.model_dump(), now_hhmm=now_hhmm)
    _log_result(result)

    log_event(
        "rag",
        "Agentic RAG assignment completed.",
        "success" if result.get("assigned") else "warning",
        {
            "assigned": result.get("assigned"),
            "resource": (result.get("assigned_resource") or {}).get("name"),
            "similar_cases": len(result.get("rag_context", {}).get("similar_cases", [])),
            "policy_chunks": len(result.get("rag_context", {}).get("policy_context", [])),
            "workflow_steps": len(result.get("workflow_trace", [])),
        },
    )

    return result


@app.post("/assign/ml")
def assign_task_with_ml_ranker(
    task: TaskIn,
    now_hhmm: Optional[str] = Query(default=None),
    model_type: Optional[str] = Query(default=None),
):
    log_event(
        "assignment",
        "ML assignment started.",
        "info",
        {
            "task": task.title,
            "priority": task.priority,
            "category": task.category,
            "time": now_hhmm,
            "requested_model_type": model_type,
        },
    )

    result = assign_task_ml(task.model_dump(), now_hhmm=now_hhmm, model_type=model_type)
    _log_result(result)

    log_event(
        "ml",
        "ML assignment completed.",
        "success" if result.get("assigned") else "warning",
        {
            "assigned": result.get("assigned"),
            "resource": (result.get("assigned_resource") or {}).get("name"),
            "score": (result.get("assigned_resource") or {}).get("score"),
            "model_type": (result.get("assigned_resource") or {}).get("model_type"),
            "warning": result.get("model_warning"),
        },
    )

    return result


@app.post("/assign/batch")
def assign_batch(payload: AssignmentRequest):
    log_event("assignment", "Batch assignment started.", "info", {"task_count": len(payload.tasks), "time": payload.now_hhmm})

    result = assign_tasks(
        [task.model_dump() for task in payload.tasks],
        now_hhmm=payload.now_hhmm,
    )

    for item in result.get("assignments", []):
        _log_result(item)

    log_event(
        "assignment",
        "Batch assignment completed.",
        "success",
        {
            "total_tasks": result.get("total_tasks"),
            "assigned_count": result.get("assigned_count"),
            "unassigned_count": result.get("unassigned_count"),
        },
    )

    return result


@app.post("/assign/sample")
def assign_sample(now_hhmm: Optional[str] = Query(default="10:30")):
    tasks = load_tasks()
    log_event("assignment", "Sample batch assignment started.", "info", {"task_count": len(tasks), "time": now_hhmm})

    result = assign_tasks(tasks, now_hhmm=now_hhmm)

    for item in result.get("assignments", []):
        _log_result(item)

    log_event(
        "assignment",
        "Sample batch assignment completed.",
        "success",
        {
            "total_tasks": result.get("total_tasks"),
            "assigned_count": result.get("assigned_count"),
            "unassigned_count": result.get("unassigned_count"),
        },
    )

    return result
