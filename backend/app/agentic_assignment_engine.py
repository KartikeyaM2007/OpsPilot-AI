from typing import Dict, Optional

from .database import load_resources
from .explanation_engine import explain_unassigned
from .rag_engine import build_rag_context
from .scoring_engine import score_resource_for_task
from .task_parser import parse_task


def _case_bonus_for_resource(resource: Dict, rag_context: Dict) -> Dict:
    name = resource.get("name", "")
    stats = rag_context.get("resource_case_stats", {}).get(name)

    if not stats:
        return {
            "bonus": 0.0,
            "reason": "no strong similar-case history found",
        }

    successful = stats.get("successful_cases", 0)
    similar = max(stats.get("similar_cases", 1), 1)
    escalations = stats.get("escalations", 0)
    avg_similarity = float(stats.get("avg_similarity") or 0)

    success_ratio = successful / similar
    escalation_penalty = escalations * 2.0

    bonus = (success_ratio * 8.0) + (avg_similarity * 6.0) - escalation_penalty
    bonus = max(-5.0, min(12.0, bonus))

    return {
        "bonus": round(bonus, 2),
        "reason": (
            f"RAG found {similar} similar past case(s), "
            f"{successful} successful, {escalations} escalated"
        ),
    }


def _workflow_step(name: str, status: str, detail: str, data=None) -> Dict:
    return {
        "name": name,
        "status": status,
        "detail": detail,
        "data": data or {},
    }


def _build_workflow_trace(parsed_task: Dict, rag_context: Dict, resources: list, candidates: list, winner: Dict | None) -> list:
    eligible = [candidate for candidate in candidates if candidate.get("eligible")]
    skipped = [candidate for candidate in candidates if not candidate.get("eligible")]

    return [
        _workflow_step(
            "Task Intake",
            "completed",
            "Received task title, description, priority, category, required skills, and SLA.",
            {
                "title": parsed_task.get("title"),
                "priority": parsed_task.get("priority"),
                "sla_minutes": parsed_task.get("sla_minutes"),
            },
        ),
        _workflow_step(
            "Task Parser Agent",
            "completed",
            "Normalized task category, priority, and required skills for downstream matching.",
            {
                "category": parsed_task.get("category"),
                "required_skills": parsed_task.get("required_skills"),
            },
        ),
        _workflow_step(
            "RAG Retriever",
            "completed",
            "Retrieved similar historical cases and relevant SOP/policy chunks.",
            {
                "similar_cases_found": len(rag_context.get("similar_cases", [])),
                "policy_chunks_found": len(rag_context.get("policy_context", [])),
            },
        ),
        _workflow_step(
            "Resource State Checker",
            "completed",
            "Checked online/offline status, idle/busy status, shift timing, and current workload.",
            {
                "resources_checked": len(resources),
                "eligible_after_constraints": len(eligible),
                "skipped_resources": len(skipped),
            },
        ),
        _workflow_step(
            "Scoring Engine",
            "completed",
            "Calculated deterministic score using skill match, availability, workload, category match, performance, experience, and speed.",
            {
                "top_candidates": [
                    {
                        "name": candidate.get("resource_name"),
                        "base_score": candidate.get("base_score", candidate.get("final_score")),
                        "rag_bonus": candidate.get("rag_bonus", 0),
                        "final_score": candidate.get("final_score"),
                        "eligible": candidate.get("eligible"),
                    }
                    for candidate in candidates[:3]
                ],
            },
        ),
        _workflow_step(
            "RAG Score Adjuster",
            "completed",
            "Adjusted eligible resource scores using similar-case success and escalation evidence.",
            {
                "rag_adjusted_candidates": [
                    {
                        "name": candidate.get("resource_name"),
                        "rag_bonus": candidate.get("rag_bonus", 0),
                        "reason": candidate.get("rag_reason", ""),
                    }
                    for candidate in candidates[:3]
                ],
            },
        ),
        _workflow_step(
            "Assignment Decision",
            "completed" if winner else "blocked",
            (
                f"Selected {winner.get('resource_name')} as the best valid resource."
                if winner
                else "No eligible resource found after constraints."
            ),
            {
                "assigned_to": winner.get("resource_name") if winner else None,
                "final_score": winner.get("final_score") if winner else None,
            },
        ),
        _workflow_step(
            "Explanation Generator",
            "completed",
            "Generated readable explanation with selected resource, skipped resources, and RAG evidence.",
            {
                "explanation_ready": True,
            },
        ),
    ]


def _explain_agentic_assignment(task: Dict, winner: Dict, rag_context: Dict, candidates: list) -> str:
    similar_cases = rag_context.get("similar_cases", [])
    policy_context = rag_context.get("policy_context", [])

    base = (
        f"Agentic RAG assigned this task to {winner.get('resource_name')} because "
        f"the agent passed shift, availability, workload, and skill checks, then received "
        f"the best combined score after similar-case retrieval. "
    )

    if winner.get("positive_reasons"):
        base += "Core reasons: " + "; ".join(winner["positive_reasons"][:4]) + ". "

    if winner.get("rag_reason"):
        base += "RAG evidence: " + winner["rag_reason"] + ". "

    if similar_cases:
        top_case = similar_cases[0]
        base += (
            f"Most similar past case: '{top_case.get('title')}' handled by "
            f"{top_case.get('resource_name')} with similarity {top_case.get('similarity_score')}. "
        )

    if policy_context:
        base += "Relevant policy/SOP context was also retrieved before scoring. "

    skipped = [
        candidate for candidate in candidates
        if not candidate.get("eligible") and candidate.get("rejection_reasons")
    ][:2]

    for item in skipped:
        base += (
            f"{item.get('resource_name')} was skipped because "
            f"{', '.join(item.get('rejection_reasons', [])[:2])}. "
        )

    return base.strip()


def assign_task_agentic(task: Dict, now_hhmm: Optional[str] = None) -> Dict:
    resources = load_resources()
    parsed_task = parse_task(task)
    rag_context = build_rag_context(parsed_task)

    candidates = []

    for resource in resources:
        candidate = score_resource_for_task(parsed_task, resource, now_hhmm=now_hhmm)
        rag_boost = _case_bonus_for_resource(resource, rag_context)

        candidate["base_score"] = candidate["final_score"]
        candidate["rag_bonus"] = rag_boost["bonus"]
        candidate["rag_reason"] = rag_boost["reason"]

        if candidate["eligible"]:
            candidate["final_score"] = round(candidate["final_score"] + rag_boost["bonus"], 2)
            candidate["breakdown"]["rag_similar_case_bonus"] = rag_boost["bonus"]
            if rag_boost["bonus"] > 0:
                candidate["positive_reasons"].append(rag_boost["reason"])

        candidates.append(candidate)

    candidates.sort(key=lambda item: item["final_score"], reverse=True)
    valid_candidates = [candidate for candidate in candidates if candidate["eligible"]]
    winner = valid_candidates[0] if valid_candidates else None
    workflow_trace = _build_workflow_trace(parsed_task, rag_context, resources, candidates, winner)

    if not winner:
        return {
            "task": parsed_task,
            "assigned": False,
            "assigned_resource": None,
            "mode": "agentic_rag",
            "explanation": explain_unassigned(parsed_task, candidates),
            "rag_context": rag_context,
            "workflow_trace": workflow_trace,
            "candidates": candidates,
        }

    return {
        "task": parsed_task,
        "assigned": True,
        "assigned_resource": {
            "resource_id": winner["resource_id"],
            "name": winner["resource_name"],
            "score": winner["final_score"],
            "base_score": winner["base_score"],
            "rag_bonus": winner["rag_bonus"],
        },
        "mode": "agentic_rag",
        "explanation": _explain_agentic_assignment(parsed_task, winner, rag_context, candidates),
        "rag_context": rag_context,
        "workflow_trace": workflow_trace,
        "candidates": candidates,
    }
