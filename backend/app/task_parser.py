from typing import Dict, List


CATEGORY_RULES = {
    "payment": {
        "keywords": ["payment", "checkout", "card", "upi", "transaction", "gateway", "failed payment"],
        "skills": ["payments", "billing", "customer_support"],
    },
    "billing": {
        "keywords": ["bill", "invoice", "refund", "subscription", "charged", "pricing"],
        "skills": ["billing", "refunds", "customer_support"],
    },
    "technical": {
        "keywords": ["bug", "error", "api", "server", "crash", "latency", "login issue", "not working"],
        "skills": ["technical_support", "api", "debugging"],
    },
    "account": {
        "keywords": ["account", "password", "login", "signup", "profile", "locked"],
        "skills": ["account_management", "customer_support"],
    },
    "general": {
        "keywords": ["question", "help", "support", "information", "query"],
        "skills": ["customer_support"],
    },
}


def _clean_list(values: List[str]) -> List[str]:
    return sorted({str(value).strip().lower() for value in values if str(value).strip()})


def parse_task(task: Dict) -> Dict:
    parsed = dict(task)
    text = f"{parsed.get('title', '')} {parsed.get('description', '')}".lower()

    detected_category = parsed.get("category")
    detected_skills = list(parsed.get("required_skills") or [])

    if not detected_category:
        best_category = "general"
        best_hits = 0

        for category, rule in CATEGORY_RULES.items():
            hits = sum(1 for keyword in rule["keywords"] if keyword in text)
            if hits > best_hits:
                best_category = category
                best_hits = hits

        detected_category = best_category

    if not detected_skills:
        detected_skills.extend(CATEGORY_RULES.get(detected_category, CATEGORY_RULES["general"])["skills"])

    priority = str(parsed.get("priority") or "medium").lower()
    if "urgent" in text or "immediately" in text or "production" in text:
        priority = "urgent"
    elif "high" in text or "critical" in text:
        priority = "high"

    parsed["category"] = detected_category
    parsed["required_skills"] = _clean_list(detected_skills)
    parsed["priority"] = priority
    parsed["sla_minutes"] = int(parsed.get("sla_minutes") or 120)

    return parsed
