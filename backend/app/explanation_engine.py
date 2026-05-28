from typing import Dict, List


def explain_assignment(task: Dict, winner: Dict, candidates: List[Dict]) -> str:
    winner_reasons = winner.get("positive_reasons") or []
    reason_text = "; ".join(winner_reasons[:5]) if winner_reasons else "highest valid score among available resources"

    rejected = [
        candidate for candidate in candidates
        if not candidate.get("eligible") and candidate.get("rejection_reasons")
    ][:3]

    rejected_text = ""
    if rejected:
        parts = []
        for candidate in rejected:
            parts.append(
                f"{candidate.get('resource_name')} was skipped because "
                f"{', '.join(candidate.get('rejection_reasons', [])[:2])}"
            )
        rejected_text = " " + " ".join(parts)

    return (
        f"Assigned to {winner.get('resource_name')} because {reason_text}. "
        f"Final score: {winner.get('final_score')}. "
        f"{rejected_text}"
    ).strip()


def explain_unassigned(task: Dict, candidates: List[Dict]) -> str:
    reasons = []
    for candidate in candidates:
        for reason in candidate.get("rejection_reasons", []):
            reasons.append(reason)

    unique_reasons = sorted(set(reasons))
    if not unique_reasons:
        return "No eligible resource found."

    return "No eligible resource found because: " + "; ".join(unique_reasons[:5])
