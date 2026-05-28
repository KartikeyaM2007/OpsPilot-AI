import random
from typing import Dict, Optional

from .llm_provider import generate_json_with_llm


TASK_FALLBACKS = [
    {
        "title": "Customer payment failed after checkout",
        "description": "Customer says the payment failed during checkout but the amount was debited from their account.",
        "priority": "high",
        "category": "payment",
        "required_skills": ["payments", "billing", "customer_support"],
        "sla_minutes": 60,
    },
    {
        "title": "Partner API latency issue",
        "description": "A partner integration reports slow API responses and intermittent timeout errors in production.",
        "priority": "urgent",
        "category": "technical",
        "required_skills": ["technical_support", "api", "debugging"],
        "sla_minutes": 45,
    },
    {
        "title": "Refund request for duplicate charge",
        "description": "Customer was charged twice for the same order and wants an urgent refund update.",
        "priority": "high",
        "category": "billing",
        "required_skills": ["billing", "refunds", "customer_support"],
        "sla_minutes": 60,
    },
    {
        "title": "User account locked after failed login attempts",
        "description": "Customer cannot access their account because it was locked after multiple login attempts.",
        "priority": "medium",
        "category": "account",
        "required_skills": ["account_management", "customer_support"],
        "sla_minutes": 120,
    },
    {
        "title": "Customer needs help using analytics dashboard",
        "description": "Customer wants guidance on how to read reports and export dashboard metrics.",
        "priority": "low",
        "category": "general",
        "required_skills": ["customer_support"],
        "sla_minutes": 240,
    },
]


RESOURCE_FALLBACKS = [
    {
        "name": "Maya",
        "status": "idle",
        "current_tasks": 0,
        "max_tasks": 4,
        "shift_start": "09:00",
        "shift_end": "18:00",
        "skills": ["payments", "billing", "customer_support"],
        "handled_categories": ["payment", "billing"],
        "experience_level": 4,
        "success_rate": 0.91,
        "avg_resolution_minutes": 38,
    },
    {
        "name": "Kabir",
        "status": "available",
        "current_tasks": 1,
        "max_tasks": 4,
        "shift_start": "10:00",
        "shift_end": "19:00",
        "skills": ["technical_support", "api", "debugging", "backend"],
        "handled_categories": ["technical"],
        "experience_level": 5,
        "success_rate": 0.94,
        "avg_resolution_minutes": 42,
    },
    {
        "name": "Isha",
        "status": "idle",
        "current_tasks": 0,
        "max_tasks": 3,
        "shift_start": "08:00",
        "shift_end": "17:00",
        "skills": ["account_management", "customer_support"],
        "handled_categories": ["account", "general"],
        "experience_level": 3,
        "success_rate": 0.86,
        "avg_resolution_minutes": 52,
    },
    {
        "name": "Dev",
        "status": "busy",
        "current_tasks": 2,
        "max_tasks": 5,
        "shift_start": "14:00",
        "shift_end": "22:00",
        "skills": ["billing", "refunds", "customer_support"],
        "handled_categories": ["billing", "refund"],
        "experience_level": 4,
        "success_rate": 0.89,
        "avg_resolution_minutes": 46,
    },
]


def _normalize_task(data: Dict, source_provider: str, llm_used: bool) -> Dict:
    fallback = random.choice(TASK_FALLBACKS)

    required_skills = data.get("required_skills", fallback["required_skills"])
    if isinstance(required_skills, str):
        required_skills = [item.strip().lower() for item in required_skills.split(",") if item.strip()]

    priority = str(data.get("priority", fallback["priority"])).lower()
    if priority not in {"urgent", "high", "medium", "low"}:
        priority = fallback["priority"]

    return {
        "title": str(data.get("title", fallback["title"])),
        "description": str(data.get("description", fallback["description"])),
        "priority": priority,
        "category": str(data.get("category", fallback["category"])).lower(),
        "required_skills": required_skills,
        "sla_minutes": int(data.get("sla_minutes", fallback["sla_minutes"]) or fallback["sla_minutes"]),
        "source_provider": source_provider,
        "llm_used": llm_used,
    }


def _normalize_resource(data: Dict, source_provider: str, llm_used: bool) -> Dict:
    fallback = random.choice(RESOURCE_FALLBACKS)

    skills = data.get("skills", fallback["skills"])
    if isinstance(skills, str):
        skills = [item.strip().lower() for item in skills.split(",") if item.strip()]

    handled_categories = data.get("handled_categories", fallback["handled_categories"])
    if isinstance(handled_categories, str):
        handled_categories = [item.strip().lower() for item in handled_categories.split(",") if item.strip()]

    status = str(data.get("status", fallback["status"])).lower()
    if status not in {"idle", "available", "busy", "offline"}:
        status = fallback["status"]

    success_rate = float(data.get("success_rate", fallback["success_rate"]) or fallback["success_rate"])
    if success_rate > 1:
        success_rate = success_rate / 100

    return {
        "name": str(data.get("name", fallback["name"])),
        "status": status,
        "current_tasks": int(data.get("current_tasks", fallback["current_tasks"]) or fallback["current_tasks"]),
        "max_tasks": int(data.get("max_tasks", fallback["max_tasks"]) or fallback["max_tasks"]),
        "shift_start": str(data.get("shift_start", fallback["shift_start"])),
        "shift_end": str(data.get("shift_end", fallback["shift_end"])),
        "skills": skills,
        "handled_categories": handled_categories,
        "experience_level": int(data.get("experience_level", fallback["experience_level"]) or fallback["experience_level"]),
        "success_rate": round(success_rate, 2),
        "avg_resolution_minutes": float(data.get("avg_resolution_minutes", fallback["avg_resolution_minutes"]) or fallback["avg_resolution_minutes"]),
        "source_provider": source_provider,
        "llm_used": llm_used,
    }


def generate_mock_task(provider: Optional[str] = None) -> Dict:
    system_prompt = (
        "You generate realistic customer support/service tasks for an AI workforce allocation demo."
    )

    user_prompt = """
Generate one realistic task for a service/customer-support task allocation system.

Return JSON with exactly:
{
  "title": string,
  "description": string,
  "priority": "urgent" | "high" | "medium" | "low",
  "category": "payment" | "billing" | "technical" | "account" | "general",
  "required_skills": string[],
  "sla_minutes": number
}

Make it different every time.
"""

    result = generate_json_with_llm(system_prompt, user_prompt, provider=provider)

    if result["ok"]:
        return _normalize_task(result["data"], result["provider"], True)

    fallback = random.choice(TASK_FALLBACKS)
    normalized = _normalize_task(fallback, result["provider"], False)
    normalized["fallback_reason"] = result["error"]
    return normalized


def generate_mock_resource(provider: Optional[str] = None) -> Dict:
    system_prompt = (
        "You generate realistic support agents/resources for an AI workforce allocation demo."
    )

    user_prompt = """
Generate one realistic support agent/resource.

Return JSON with exactly:
{
  "name": string,
  "status": "idle" | "available" | "busy" | "offline",
  "current_tasks": number,
  "max_tasks": number,
  "shift_start": "HH:MM",
  "shift_end": "HH:MM",
  "skills": string[],
  "handled_categories": string[],
  "experience_level": number,
  "success_rate": number,
  "avg_resolution_minutes": number
}

Use realistic values. success_rate must be between 0 and 1.
Make it different every time.
"""

    result = generate_json_with_llm(system_prompt, user_prompt, provider=provider)

    if result["ok"]:
        return _normalize_resource(result["data"], result["provider"], True)

    fallback = random.choice(RESOURCE_FALLBACKS)
    normalized = _normalize_resource(fallback, result["provider"], False)
    normalized["fallback_reason"] = result["error"]
    return normalized
