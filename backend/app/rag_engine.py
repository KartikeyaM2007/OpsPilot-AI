import math
from pathlib import Path
from typing import Dict, List

from .database import load_past_cases


DATA_DIR = Path(__file__).resolve().parents[2] / "data"
POLICY_PATH = DATA_DIR / "knowledge_base" / "support_policy.txt"


def _tokenize(text: str) -> set:
    clean = ""
    for char in str(text).lower():
        clean += char if char.isalnum() else " "
    return {token for token in clean.split() if len(token) > 2}


def _similarity(a: str, b: str) -> float:
    a_tokens = _tokenize(a)
    b_tokens = _tokenize(b)

    if not a_tokens or not b_tokens:
        return 0.0

    overlap = len(a_tokens.intersection(b_tokens))
    denominator = math.sqrt(len(a_tokens) * len(b_tokens))
    return round(overlap / denominator, 4)


def _read_policy() -> str:
    if not POLICY_PATH.exists():
        return ""

    return POLICY_PATH.read_text(encoding="utf-8")


def retrieve_similar_cases(task: Dict, top_k: int = 5) -> List[Dict]:
    cases = load_past_cases()
    query = " ".join([
        str(task.get("title", "")),
        str(task.get("description", "")),
        str(task.get("category", "")),
        " ".join(task.get("required_skills", []) or []),
    ])

    scored = []
    for case in cases:
        case_text = " ".join([
            case.get("title", ""),
            case.get("description", ""),
            case.get("category", ""),
            case.get("skills", ""),
            case.get("resolution_notes", ""),
        ])

        score = _similarity(query, case_text)

        if str(task.get("category", "")).lower() == str(case.get("category", "")).lower():
            score += 0.15

        scored.append({
            **case,
            "similarity_score": round(min(score, 1.0), 4),
        })

    scored.sort(key=lambda item: item["similarity_score"], reverse=True)
    return [item for item in scored[:top_k] if item["similarity_score"] > 0]


def retrieve_policy_context(task: Dict) -> List[str]:
    policy_text = _read_policy()
    if not policy_text:
        return []

    chunks = [chunk.strip() for chunk in policy_text.split("\n\n") if chunk.strip()]

    query = " ".join([
        str(task.get("title", "")),
        str(task.get("description", "")),
        str(task.get("category", "")),
        str(task.get("priority", "")),
    ])

    scored_chunks = [
        {"text": chunk, "score": _similarity(query, chunk)}
        for chunk in chunks
    ]

    scored_chunks.sort(key=lambda item: item["score"], reverse=True)
    return [item["text"] for item in scored_chunks[:3] if item["score"] > 0]


def build_rag_context(task: Dict) -> Dict:
    similar_cases = retrieve_similar_cases(task)
    policy_context = retrieve_policy_context(task)
    resource_case_stats = {}

    for case in similar_cases:
        resource_name = case.get("resource_name", "")
        if not resource_name:
            continue

        stats = resource_case_stats.setdefault(resource_name, {
            "similar_cases": 0,
            "successful_cases": 0,
            "escalations": 0,
            "avg_resolution_minutes": [],
            "similarity_total": 0.0,
        })

        stats["similar_cases"] += 1
        stats["similarity_total"] += float(case.get("similarity_score") or 0)

        if str(case.get("success", "")).lower() == "true":
            stats["successful_cases"] += 1

        if str(case.get("escalated", "")).lower() == "true":
            stats["escalations"] += 1

        try:
            stats["avg_resolution_minutes"].append(float(case.get("completed_minutes") or 0))
        except ValueError:
            pass

    for stats in resource_case_stats.values():
        values = stats["avg_resolution_minutes"]
        stats["avg_resolution_minutes"] = round(sum(values) / len(values), 2) if values else None
        stats["avg_similarity"] = round(stats["similarity_total"] / max(stats["similar_cases"], 1), 4)

    return {
        "similar_cases": similar_cases,
        "policy_context": policy_context,
        "resource_case_stats": resource_case_stats,
    }
