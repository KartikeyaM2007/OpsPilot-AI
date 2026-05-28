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
