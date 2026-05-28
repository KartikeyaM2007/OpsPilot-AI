from datetime import datetime
from typing import Dict, Optional


PRIORITY_VALUE = {
    "urgent": 4,
    "high": 3,
    "medium": 2,
    "low": 1,
}


def priority_value(priority: str) -> int:
    return PRIORITY_VALUE.get(str(priority).lower(), 2)


def _parse_hhmm(value: str) -> int:
    hour, minute = value.split(":")
    return int(hour) * 60 + int(minute)


def _is_on_shift(now_hhmm: str, shift_start: str, shift_end: str) -> bool:
    now = _parse_hhmm(now_hhmm)
    start = _parse_hhmm(shift_start)
    end = _parse_hhmm(shift_end)

    if start <= end:
        return start <= now <= end

    return now >= start or now <= end


def _current_hhmm() -> str:
    return datetime.now().strftime("%H:%M")


def score_resource_for_task(task: Dict, resource: Dict, now_hhmm: Optional[str] = None) -> Dict:
    now_hhmm = now_hhmm or _current_hhmm()

    required_skills = set(task.get("required_skills") or [])
    resource_skills = set(resource.get("skills") or [])
    handled_categories = set(resource.get("handled_categories") or [])

    current_tasks = int(resource.get("current_tasks") or 0)
    max_tasks = max(int(resource.get("max_tasks") or 1), 1)
    status = str(resource.get("status") or "offline").lower()
    category = str(task.get("category") or "general").lower()

    positive_reasons = []
    rejection_reasons = []

    on_shift = _is_on_shift(
        now_hhmm,
        str(resource.get("shift_start") or "00:00"),
        str(resource.get("shift_end") or "23:59"),
    )

    if status == "offline":
        rejection_reasons.append("resource is offline")

    if not on_shift:
        rejection_reasons.append("resource is outside shift timing")

    if current_tasks >= max_tasks:
        rejection_reasons.append("resource is already at max workload")

    if required_skills:
        matched_skills = required_skills.intersection(resource_skills)
        skill_match_score = len(matched_skills) / len(required_skills)
    else:
        matched_skills = set()
        skill_match_score = 0.60

    if required_skills and not matched_skills:
        rejection_reasons.append("no required skill match")

    category_match_score = 1.0 if category in handled_categories else 0.45

    if status == "idle":
        availability_score = 1.0
        positive_reasons.append("currently idle")
    elif status == "available":
        availability_score = 0.85
        positive_reasons.append("available")
    elif status == "busy":
        availability_score = 0.45
    else:
        availability_score = 0.0

    workload_score = max(0.0, 1.0 - (current_tasks / max_tasks))
    performance_score = float(resource.get("success_rate") or 0.5)
    experience_score = min(float(resource.get("experience_level") or 1) / 5.0, 1.0)

    avg_resolution = float(resource.get("avg_resolution_minutes") or 120)
    speed_score = max(0.0, 1.0 - min(avg_resolution / 240.0, 1.0))

    if matched_skills:
        positive_reasons.append(f"matched skills: {', '.join(sorted(matched_skills))}")

    if category_match_score == 1.0:
        positive_reasons.append(f"has past experience in {category} tasks")

    if workload_score >= 0.70:
        positive_reasons.append("low current workload")

    if performance_score >= 0.85:
        positive_reasons.append("strong past success rate")

    final_score = 100 * (
        skill_match_score * 0.30
        + availability_score * 0.20
        + workload_score * 0.15
        + category_match_score * 0.15
        + performance_score * 0.10
        + experience_score * 0.05
        + speed_score * 0.05
    )

    if priority_value(task.get("priority")) >= 3 and skill_match_score < 0.35:
        final_score -= 20
        rejection_reasons.append("skill match is too weak for high priority task")

    eligible = len(rejection_reasons) == 0

    if not eligible:
        final_score = 0.0

    return {
        "resource_id": resource.get("resource_id"),
        "resource_name": resource.get("name"),
        "eligible": eligible,
        "final_score": round(final_score, 2),
        "breakdown": {
            "skill_match": round(skill_match_score, 2),
            "availability": round(availability_score, 2),
            "workload": round(workload_score, 2),
            "category_match": round(category_match_score, 2),
            "past_performance": round(performance_score, 2),
            "experience": round(experience_score, 2),
            "speed": round(speed_score, 2),
        },
        "positive_reasons": positive_reasons,
        "rejection_reasons": rejection_reasons,
    }
