import csv
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


DATA_DIR = Path(__file__).resolve().parents[2] / "data"
DB_PATH = DATA_DIR / "app.db"

RESOURCE_FIELDS = [
    "resource_id", "name", "skills", "experience_level", "status",
    "current_tasks", "max_tasks", "shift_start", "shift_end",
    "success_rate", "avg_resolution_minutes", "handled_categories",
]

TASK_FIELDS = [
    "task_id", "title", "description", "priority", "category",
    "required_skills", "sla_minutes",
]

TASK_HISTORY_FIELDS = [
    "history_id", "task_id", "resource_id", "category",
    "completed_minutes", "success", "customer_rating", "escalated",
]

PAST_CASE_FIELDS = [
    "case_id", "title", "description", "category", "skills",
    "resource_name", "completed_minutes", "success", "customer_rating",
    "escalated", "resolution_notes",
]

ASSIGNMENT_LOG_FIELDS = [
    "log_id", "timestamp", "mode", "task_title", "task_category",
    "task_priority", "required_skills", "assigned", "assigned_resource",
    "score", "base_score", "rag_bonus", "explanation",
]

ML_TRAINING_FIELDS = [
    "row_id", "timestamp", "mode", "task_title", "task_category",
    "task_priority", "candidate_resource_id", "candidate_resource_name",
    "priority_value", "eligible", "base_score", "rag_bonus",
    "deterministic_score", "skill_match", "availability", "workload",
    "category_match", "past_performance", "experience", "speed",
    "rejection_count", "label_selected",
]


def _connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _split_list(value: Any) -> List[str]:
    if value is None:
        return []
    return [item.strip().lower() for item in str(value).replace(",", ";").split(";") if item.strip()]


def _join_list(value: Any) -> str:
    if isinstance(value, list):
        return ";".join(str(item).strip().lower() for item in value if str(item).strip())
    return str(value or "")


def _read_csv(filename: str) -> List[Dict[str, Any]]:
    path = DATA_DIR / filename
    if not path.exists():
        return []

    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def _table_count(conn: sqlite3.Connection, table: str) -> int:
    row = conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()
    return int(row["count"])


def _insert_many(conn: sqlite3.Connection, table: str, fields: List[str], rows: List[Dict[str, Any]]) -> None:
    if not rows:
        return

    placeholders = ", ".join(["?"] * len(fields))
    columns = ", ".join(fields)
    sql = f"INSERT OR REPLACE INTO {table} ({columns}) VALUES ({placeholders})"
    values = [[row.get(field, "") for field in fields] for row in rows]
    conn.executemany(sql, values)


def init_db() -> None:
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS resources (
                resource_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                skills TEXT,
                experience_level INTEGER,
                status TEXT,
                current_tasks INTEGER,
                max_tasks INTEGER,
                shift_start TEXT,
                shift_end TEXT,
                success_rate REAL,
                avg_resolution_minutes REAL,
                handled_categories TEXT
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                task_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT,
                priority TEXT,
                category TEXT,
                required_skills TEXT,
                sla_minutes INTEGER
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS task_history (
                history_id TEXT PRIMARY KEY,
                task_id TEXT,
                resource_id TEXT,
                category TEXT,
                completed_minutes REAL,
                success TEXT,
                customer_rating REAL,
                escalated TEXT
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS past_cases (
                case_id TEXT PRIMARY KEY,
                title TEXT,
                description TEXT,
                category TEXT,
                skills TEXT,
                resource_name TEXT,
                completed_minutes REAL,
                success TEXT,
                customer_rating REAL,
                escalated TEXT,
                resolution_notes TEXT
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS assignment_logs (
                log_id TEXT PRIMARY KEY,
                timestamp TEXT,
                mode TEXT,
                task_title TEXT,
                task_category TEXT,
                task_priority TEXT,
                required_skills TEXT,
                assigned TEXT,
                assigned_resource TEXT,
                score TEXT,
                base_score TEXT,
                rag_bonus TEXT,
                explanation TEXT
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS ml_training_candidates (
                row_id TEXT PRIMARY KEY,
                timestamp TEXT,
                mode TEXT,
                task_title TEXT,
                task_category TEXT,
                task_priority TEXT,
                candidate_resource_id TEXT,
                candidate_resource_name TEXT,
                priority_value REAL,
                eligible REAL,
                base_score REAL,
                rag_bonus REAL,
                deterministic_score REAL,
                skill_match REAL,
                availability REAL,
                workload REAL,
                category_match REAL,
                past_performance REAL,
                experience REAL,
                speed REAL,
                rejection_count REAL,
                label_selected INTEGER
            )
        """)

        if _table_count(conn, "resources") == 0:
            _insert_many(conn, "resources", RESOURCE_FIELDS, _read_csv("sample_resources.csv"))
        if _table_count(conn, "tasks") == 0:
            _insert_many(conn, "tasks", TASK_FIELDS, _read_csv("sample_tasks.csv"))
        if _table_count(conn, "task_history") == 0:
            _insert_many(conn, "task_history", TASK_HISTORY_FIELDS, _read_csv("task_history.csv"))
        if _table_count(conn, "past_cases") == 0:
            _insert_many(conn, "past_cases", PAST_CASE_FIELDS, _read_csv("past_cases.csv"))
        if _table_count(conn, "assignment_logs") == 0:
            _insert_many(conn, "assignment_logs", ASSIGNMENT_LOG_FIELDS, _read_csv("assignment_logs.csv"))
        if _table_count(conn, "ml_training_candidates") == 0:
            _insert_many(conn, "ml_training_candidates", ML_TRAINING_FIELDS, _read_csv("ml_training_candidates.csv"))

        conn.commit()


def _fetch_all(table: str, order_by: Optional[str] = None, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    init_db()
    sql = f"SELECT * FROM {table}"
    if order_by:
        sql += f" ORDER BY {order_by}"
    if limit:
        sql += f" LIMIT {int(limit)}"

    with _connect() as conn:
        rows = conn.execute(sql).fetchall()

    return [dict(row) for row in rows]


def load_resources() -> List[Dict[str, Any]]:
    rows = _fetch_all("resources", order_by="resource_id ASC")

    for row in rows:
        row["skills"] = _split_list(row.get("skills"))
        row["handled_categories"] = _split_list(row.get("handled_categories"))
        row["experience_level"] = int(float(row.get("experience_level") or 1))
        row["current_tasks"] = int(float(row.get("current_tasks") or 0))
        row["max_tasks"] = int(float(row.get("max_tasks") or 3))
        row["success_rate"] = float(row.get("success_rate") or 0.5)
        row["avg_resolution_minutes"] = float(row.get("avg_resolution_minutes") or 120)
        row["status"] = str(row.get("status") or "offline").lower()

    return rows


def save_resources(resources: List[Dict[str, Any]]) -> None:
    init_db()

    rows = []
    for resource in resources:
        row = dict(resource)
        row["skills"] = _join_list(row.get("skills"))
        row["handled_categories"] = _join_list(row.get("handled_categories"))
        rows.append({field: row.get(field, "") for field in RESOURCE_FIELDS})

    with _connect() as conn:
        conn.execute("DELETE FROM resources")
        _insert_many(conn, "resources", RESOURCE_FIELDS, rows)
        conn.commit()


def load_tasks() -> List[Dict[str, Any]]:
    rows = _fetch_all("tasks", order_by="task_id ASC")

    for row in rows:
        row["required_skills"] = _split_list(row.get("required_skills"))
        row["sla_minutes"] = int(float(row.get("sla_minutes") or 120))

    return rows


def load_history() -> List[Dict[str, Any]]:
    return _fetch_all("task_history", order_by="history_id ASC")


def load_past_cases() -> List[Dict[str, Any]]:
    return _fetch_all("past_cases", order_by="case_id ASC")


def load_assignment_logs(limit: int = 50) -> List[Dict[str, Any]]:
    return _fetch_all("assignment_logs", order_by="timestamp DESC", limit=limit)


def append_assignment_log(result: Dict[str, Any]) -> Dict[str, Any]:
    init_db()

    task = result.get("task", {}) or {}
    assigned_resource = result.get("assigned_resource") or {}

    log_row = {
        "log_id": datetime.now().strftime("%Y%m%d%H%M%S%f"),
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "mode": result.get("mode") or "normal_scoring",
        "task_title": task.get("title", ""),
        "task_category": task.get("category", ""),
        "task_priority": task.get("priority", ""),
        "required_skills": ", ".join(task.get("required_skills", []) or []),
        "assigned": str(result.get("assigned", False)),
        "assigned_resource": assigned_resource.get("name", "") if assigned_resource else "",
        "score": assigned_resource.get("score", "") if assigned_resource else "",
        "base_score": assigned_resource.get("base_score", "") if assigned_resource else "",
        "rag_bonus": assigned_resource.get("rag_bonus", "") if assigned_resource else "",
        "explanation": result.get("explanation", ""),
    }

    with _connect() as conn:
        _insert_many(conn, "assignment_logs", ASSIGNMENT_LOG_FIELDS, [log_row])
        conn.commit()

    return log_row


def load_ml_training_rows() -> List[Dict[str, Any]]:
    return _fetch_all("ml_training_candidates", order_by="timestamp ASC")


def append_ml_training_rows(rows: List[Dict[str, Any]]) -> int:
    init_db()
    clean_rows = [{field: row.get(field, "") for field in ML_TRAINING_FIELDS} for row in rows]

    with _connect() as conn:
        _insert_many(conn, "ml_training_candidates", ML_TRAINING_FIELDS, clean_rows)
        conn.commit()

    return len(clean_rows)


def clear_ml_training_rows() -> None:
    init_db()
    with _connect() as conn:
        conn.execute("DELETE FROM ml_training_candidates")
        conn.commit()


def get_db_status() -> Dict[str, Any]:
    init_db()

    tables = [
        "resources", "tasks", "task_history", "past_cases",
        "assignment_logs", "ml_training_candidates",
    ]

    with _connect() as conn:
        counts = {table: _table_count(conn, table) for table in tables}

    return {
        "database_path": str(DB_PATH),
        "database_exists": DB_PATH.exists(),
        "tables": counts,
        "storage": "sqlite",
    }


init_db()
