from typing import Dict, List, Optional

from .database import load_resources
from .explanation_engine import explain_assignment, explain_unassigned
from .scoring_engine import priority_value, score_resource_for_task
from .task_parser import parse_task


def _increment_resource_load(resources: List[Dict], resource_id: str) -> None:
    for resource in resources:
        if resource.get("resource_id") == resource_id:
            resource["current_tasks"] = int(resource.get("current_tasks") or 0) + 1
            if resource["current_tasks"] > 0 and resource.get("status") == "idle":
                resource["status"] = "busy"
            return


def assign_tasks(
    tasks: List[Dict],
    resources: Optional[List[Dict]] = None,
    now_hhmm: Optional[str] = None,
) -> Dict:
    resources = resources or load_resources()
    parsed_tasks = [parse_task(task) for task in tasks]

    parsed_tasks.sort(key=lambda task: priority_value(task.get("priority")), reverse=True)

    assignments = []

    for task in parsed_tasks:
        candidates = [
            score_resource_for_task(task, resource, now_hhmm=now_hhmm)
            for resource in resources
        ]
        candidates.sort(key=lambda item: item["final_score"], reverse=True)

        valid_candidates = [candidate for candidate in candidates if candidate["eligible"]]

        if valid_candidates:
            winner = valid_candidates[0]
            _increment_resource_load(resources, winner["resource_id"])

            assignments.append({
                "task": task,
                "assigned": True,
                "assigned_resource": {
                    "resource_id": winner["resource_id"],
                    "name": winner["resource_name"],
                    "score": winner["final_score"],
                },
                "explanation": explain_assignment(task, winner, candidates),
                "candidates": candidates,
            })
        else:
            assignments.append({
                "task": task,
                "assigned": False,
                "assigned_resource": None,
                "explanation": explain_unassigned(task, candidates),
                "candidates": candidates,
            })

    return {
        "total_tasks": len(parsed_tasks),
        "assigned_count": sum(1 for item in assignments if item["assigned"]),
        "unassigned_count": sum(1 for item in assignments if not item["assigned"]),
        "assignments": assignments,
        "updated_resource_state": resources,
    }


def assign_single_task(task: Dict, now_hhmm: Optional[str] = None) -> Dict:
    result = assign_tasks([task], now_hhmm=now_hhmm)
    return result["assignments"][0]
