from collections import deque
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4


_EVENTS = deque(maxlen=700)


def log_event(
    source: str,
    message: str,
    level: str = "info",
    data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    event = {
        "id": str(uuid4()),
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "level": level,
        "source": source,
        "message": message,
        "data": data or {},
    }

    _EVENTS.append(event)
    return event


def get_events(limit: int = 150) -> List[Dict[str, Any]]:
    limit = max(1, min(int(limit), 700))
    return list(_EVENTS)[-limit:]


def clear_events() -> None:
    _EVENTS.clear()
    log_event("system", "Terminal event stream cleared.", "warning")


def seed_startup_events() -> None:
    if _EVENTS:
        return

    log_event("system", "Backend event logger initialized.")
    log_event("api", "FastAPI application loaded.")
