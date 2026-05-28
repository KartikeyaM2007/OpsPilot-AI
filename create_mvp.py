from pathlib import Path
from textwrap import dedent

ROOT = Path(__file__).resolve().parent


def write_file(relative_path: str, content: str):
    path = ROOT / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dedent(content).strip() + "\n", encoding="utf-8")
    print(f"written: {relative_path}")


FILES = {
    "backend/requirements.txt": r"""
        fastapi
        uvicorn[standard]
        pydantic
        pandas
    """,

    "backend/app/__init__.py": r"""
    """,

    "backend/app/schemas.py": r"""
        from typing import List, Optional
        from pydantic import BaseModel, Field


        class TaskIn(BaseModel):
            task_id: str = ""
            title: str
            description: str = ""
            priority: str = "medium"
            category: Optional[str] = None
            required_skills: List[str] = Field(default_factory=list)
            sla_minutes: int = 120


        class AssignmentRequest(BaseModel):
            tasks: List[TaskIn]
            now_hhmm: Optional[str] = None
    """,

    "backend/app/models.py": r"""
        from dataclasses import dataclass, field
        from typing import Dict, List


        @dataclass
        class CandidateScore:
            resource_id: str
            resource_name: str
            eligible: bool
            final_score: float
            breakdown: Dict[str, float] = field(default_factory=dict)
            positive_reasons: List[str] = field(default_factory=list)
            rejection_reasons: List[str] = field(default_factory=list)
    """,

    "backend/app/database.py": r"""
        import csv
        from pathlib import Path
        from typing import Any, Dict, List


        DATA_DIR = Path(__file__).resolve().parents[2] / "data"


        def _split_list(value: Any) -> List[str]:
            if value is None:
                return []
            return [item.strip().lower() for item in str(value).split(";") if item.strip()]


        def _join_list(value: Any) -> str:
            if isinstance(value, list):
                return ";".join(str(item) for item in value)
            return str(value or "")


        def _read_csv(filename: str) -> List[Dict[str, Any]]:
            path = DATA_DIR / filename
            if not path.exists():
                return []

            with path.open("r", encoding="utf-8-sig", newline="") as file:
                return list(csv.DictReader(file))


        def load_tasks() -> List[Dict[str, Any]]:
            rows = _read_csv("sample_tasks.csv")
            for row in rows:
                row["required_skills"] = _split_list(row.get("required_skills"))
                row["sla_minutes"] = int(row.get("sla_minutes") or 120)
            return rows


        def load_resources() -> List[Dict[str, Any]]:
            rows = _read_csv("sample_resources.csv")
            for row in rows:
                row["skills"] = _split_list(row.get("skills"))
                row["handled_categories"] = _split_list(row.get("handled_categories"))
                row["experience_level"] = int(row.get("experience_level") or 1)
                row["current_tasks"] = int(row.get("current_tasks") or 0)
                row["max_tasks"] = int(row.get("max_tasks") or 3)
                row["success_rate"] = float(row.get("success_rate") or 0.5)
                row["avg_resolution_minutes"] = float(row.get("avg_resolution_minutes") or 120)
                row["status"] = str(row.get("status") or "offline").lower()
            return rows


        def load_history() -> List[Dict[str, Any]]:
            return _read_csv("task_history.csv")


        def save_resources(resources: List[Dict[str, Any]]) -> None:
            path = DATA_DIR / "sample_resources.csv"
            path.parent.mkdir(parents=True, exist_ok=True)

            fieldnames = [
                "resource_id",
                "name",
                "skills",
                "experience_level",
                "status",
                "current_tasks",
                "max_tasks",
                "shift_start",
                "shift_end",
                "success_rate",
                "avg_resolution_minutes",
                "handled_categories",
            ]

            with path.open("w", encoding="utf-8", newline="") as file:
                writer = csv.DictWriter(file, fieldnames=fieldnames)
                writer.writeheader()

                for resource in resources:
                    row = dict(resource)
                    row["skills"] = _join_list(row.get("skills"))
                    row["handled_categories"] = _join_list(row.get("handled_categories"))
                    writer.writerow({key: row.get(key, "") for key in fieldnames})
    """,

    "backend/app/task_parser.py": r"""
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
    """,

    "backend/app/scoring_engine.py": r"""
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
    """,

    "backend/app/explanation_engine.py": r"""
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
    """,

    "backend/app/assignment_engine.py": r"""
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
    """,

    "backend/app/main.py": r"""
        from typing import Optional

        from fastapi import FastAPI, Query
        from fastapi.middleware.cors import CORSMiddleware

        from .assignment_engine import assign_single_task, assign_tasks
        from .database import load_history, load_resources, load_tasks
        from .schemas import AssignmentRequest, TaskIn


        app = FastAPI(
            title="AI Task Allocation System",
            description="Smart workforce task allocation using availability, shift timing, workload, skills, and past performance.",
            version="1.0.0",
        )

        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )


        @app.get("/")
        def health_check():
            return {
                "status": "ok",
                "app": "AI Task Allocation System",
                "message": "Backend is running. Open /docs for API testing.",
            }


        @app.get("/resources")
        def get_resources():
            return load_resources()


        @app.get("/tasks")
        def get_tasks():
            return load_tasks()


        @app.get("/history")
        def get_history():
            return load_history()


        @app.post("/assign")
        def assign_task(task: TaskIn, now_hhmm: Optional[str] = Query(default=None)):
            return assign_single_task(task.model_dump(), now_hhmm=now_hhmm)


        @app.post("/assign/batch")
        def assign_batch(payload: AssignmentRequest):
            return assign_tasks(
                [task.model_dump() for task in payload.tasks],
                now_hhmm=payload.now_hhmm,
            )


        @app.post("/assign/sample")
        def assign_sample(now_hhmm: Optional[str] = Query(default="10:30")):
            return assign_tasks(load_tasks(), now_hhmm=now_hhmm)
    """,

    "data/sample_resources.csv": r"""
        resource_id,name,skills,experience_level,status,current_tasks,max_tasks,shift_start,shift_end,success_rate,avg_resolution_minutes,handled_categories
        R1,Amit,"billing;payments;refunds;customer_support",4,idle,0,3,09:00,18:00,0.92,34,"payment;billing;refund"
        R2,Rohit,"technical_support;api;debugging;payments;backend",5,busy,2,3,09:00,18:00,0.95,45,"technical;payment"
        R3,Neha,"customer_support;account_management;general",3,idle,0,4,09:00,18:00,0.86,50,"account;general"
        R4,Priya,"billing;customer_support;refunds",4,offline,0,3,14:00,22:00,0.90,38,"billing;refund"
        R5,Joe,"technical_support;api;customer_support;debugging",3,available,1,4,09:00,18:00,0.82,60,"technical;general"
    """,

    "data/sample_tasks.csv": r"""
        task_id,title,description,priority,category,required_skills,sla_minutes
        T1,Customer payment failed,Customer says payment failed after checkout using card,high,payment,"payments;billing;customer_support",60
        T2,Login not working,User cannot login and account may be locked,medium,account,"account_management;customer_support",120
        T3,API latency issue,Partner reports API response is slow and sometimes timing out,urgent,technical,"technical_support;api;debugging",45
        T4,Refund request,Customer was charged twice and wants refund,medium,billing,"billing;refunds;customer_support",180
        T5,General product question,Customer is asking how to use the dashboard,low,general,"customer_support",240
    """,

    "data/task_history.csv": r"""
        history_id,task_id,resource_id,category,completed_minutes,success,customer_rating,escalated
        H1,T_old_1,R1,payment,30,true,5,false
        H2,T_old_2,R2,technical,40,true,5,false
        H3,T_old_3,R3,account,55,true,4,false
        H4,T_old_4,R4,billing,35,true,5,false
        H5,T_old_5,R5,technical,70,true,4,true
    """,

    "frontend/package.json": r"""
        {
          "name": "ai-task-allocation-frontend",
          "version": "1.0.0",
          "private": true,
          "type": "module",
          "scripts": {
            "dev": "vite --host 0.0.0.0",
            "build": "vite build",
            "preview": "vite preview"
          },
          "dependencies": {
            "@vitejs/plugin-react": "latest",
            "vite": "latest",
            "react": "latest",
            "react-dom": "latest"
          },
          "devDependencies": {}
        }
    """,

    "frontend/index.html": r"""
        <!doctype html>
        <html lang="en">
          <head>
            <meta charset="UTF-8" />
            <meta name="viewport" content="width=device-width, initial-scale=1.0" />
            <title>AI Task Allocation System</title>
          </head>
          <body>
            <div id="root"></div>
            <script type="module" src="/src/main.jsx"></script>
          </body>
        </html>
    """,

    "frontend/src/api/client.js": r"""
        const API_BASE = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";

        export async function apiGet(path) {
          const response = await fetch(`${API_BASE}${path}`);
          if (!response.ok) {
            throw new Error(`GET ${path} failed`);
          }
          return response.json();
        }

        export async function apiPost(path, body = null) {
          const response = await fetch(`${API_BASE}${path}`, {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
            },
            body: body ? JSON.stringify(body) : null,
          });

          if (!response.ok) {
            throw new Error(`POST ${path} failed`);
          }

          return response.json();
        }
    """,

    "frontend/src/components/ResourceTable.jsx": r"""
        export default function ResourceTable({ resources }) {
          return (
            <div className="card">
              <h2>Resources / Agents</h2>
              <div className="tableWrap">
                <table>
                  <thead>
                    <tr>
                      <th>Name</th>
                      <th>Status</th>
                      <th>Workload</th>
                      <th>Shift</th>
                      <th>Skills</th>
                      <th>Success</th>
                    </tr>
                  </thead>
                  <tbody>
                    {resources.map((resource) => (
                      <tr key={resource.resource_id}>
                        <td>{resource.name}</td>
                        <td>
                          <span className={`pill ${resource.status}`}>{resource.status}</span>
                        </td>
                        <td>{resource.current_tasks}/{resource.max_tasks}</td>
                        <td>{resource.shift_start} - {resource.shift_end}</td>
                        <td>{resource.skills?.join(", ")}</td>
                        <td>{Math.round(Number(resource.success_rate) * 100)}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          );
        }
    """,

    "frontend/src/components/TaskTable.jsx": r"""
        export default function TaskTable({ tasks }) {
          return (
            <div className="card">
              <h2>Incoming Tasks</h2>
              <div className="tableWrap">
                <table>
                  <thead>
                    <tr>
                      <th>Task</th>
                      <th>Priority</th>
                      <th>Category</th>
                      <th>Required Skills</th>
                      <th>SLA</th>
                    </tr>
                  </thead>
                  <tbody>
                    {tasks.map((task) => (
                      <tr key={task.task_id}>
                        <td>
                          <strong>{task.title}</strong>
                          <div className="muted">{task.description}</div>
                        </td>
                        <td>{task.priority}</td>
                        <td>{task.category}</td>
                        <td>{Array.isArray(task.required_skills) ? task.required_skills.join(", ") : task.required_skills}</td>
                        <td>{task.sla_minutes} min</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          );
        }
    """,

    "frontend/src/components/AssignmentCard.jsx": r"""
        export default function AssignmentCard({ item }) {
          const topCandidates = item.candidates?.slice(0, 3) || [];

          return (
            <div className="assignmentCard">
              <div className="assignmentHeader">
                <div>
                  <h3>{item.task.title}</h3>
                  <p>{item.task.category} • {item.task.priority}</p>
                </div>

                {item.assigned ? (
                  <div className="assignedBox">
                    <span>Assigned to</span>
                    <strong>{item.assigned_resource.name}</strong>
                    <small>Score {item.assigned_resource.score}</small>
                  </div>
                ) : (
                  <div className="unassignedBox">Unassigned</div>
                )}
              </div>

              <p className="explanation">{item.explanation}</p>

              <div className="candidateGrid">
                {topCandidates.map((candidate) => (
                  <div className="candidate" key={candidate.resource_id}>
                    <strong>{candidate.resource_name}</strong>
                    <span>{candidate.eligible ? "Eligible" : "Skipped"}</span>
                    <b>{candidate.final_score}</b>
                    <small>
                      {candidate.eligible
                        ? candidate.positive_reasons?.slice(0, 2).join(", ")
                        : candidate.rejection_reasons?.slice(0, 2).join(", ")}
                    </small>
                  </div>
                ))}
              </div>
            </div>
          );
        }
    """,

    "frontend/src/styles.css": r"""
        * {
          box-sizing: border-box;
        }

        body {
          margin: 0;
          font-family: Inter, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
          background: #0b1020;
          color: #e5e7eb;
        }

        .app {
          min-height: 100vh;
          padding: 32px;
        }

        .hero {
          display: flex;
          justify-content: space-between;
          gap: 24px;
          align-items: center;
          margin-bottom: 24px;
        }

        .hero h1 {
          margin: 0 0 8px;
          font-size: 36px;
        }

        .hero p {
          margin: 0;
          color: #9ca3af;
          max-width: 760px;
        }

        .controls {
          display: flex;
          gap: 12px;
          align-items: center;
        }

        .controls input {
          background: #111827;
          border: 1px solid #374151;
          border-radius: 12px;
          padding: 12px;
          color: #fff;
        }

        button {
          border: 0;
          border-radius: 12px;
          padding: 12px 18px;
          background: #60a5fa;
          color: #07111f;
          font-weight: 800;
          cursor: pointer;
        }

        button:disabled {
          opacity: 0.6;
          cursor: wait;
        }

        .grid {
          display: grid;
          grid-template-columns: 1fr;
          gap: 18px;
        }

        .card,
        .assignmentCard {
          background: rgba(17, 24, 39, 0.9);
          border: 1px solid #263244;
          border-radius: 18px;
          padding: 18px;
          box-shadow: 0 20px 60px rgba(0, 0, 0, 0.24);
        }

        .card h2 {
          margin-top: 0;
        }

        .tableWrap {
          overflow: auto;
        }

        table {
          width: 100%;
          border-collapse: collapse;
        }

        th,
        td {
          text-align: left;
          padding: 12px;
          border-bottom: 1px solid #263244;
          vertical-align: top;
        }

        th {
          color: #93c5fd;
          font-size: 13px;
          text-transform: uppercase;
          letter-spacing: 0.04em;
        }

        .muted {
          margin-top: 4px;
          color: #9ca3af;
          font-size: 13px;
        }

        .pill {
          display: inline-block;
          padding: 5px 9px;
          border-radius: 999px;
          background: #374151;
          text-transform: capitalize;
        }

        .pill.idle {
          background: #064e3b;
          color: #a7f3d0;
        }

        .pill.available {
          background: #1e3a8a;
          color: #bfdbfe;
        }

        .pill.busy {
          background: #713f12;
          color: #fde68a;
        }

        .pill.offline {
          background: #4b5563;
          color: #d1d5db;
        }

        .results {
          display: grid;
          gap: 16px;
        }

        .assignmentHeader {
          display: flex;
          justify-content: space-between;
          gap: 16px;
        }

        .assignmentHeader h3 {
          margin: 0;
        }

        .assignmentHeader p {
          color: #9ca3af;
        }

        .assignedBox,
        .unassignedBox {
          min-width: 150px;
          border-radius: 16px;
          padding: 14px;
          background: #062d24;
          color: #a7f3d0;
        }

        .assignedBox span,
        .assignedBox small {
          display: block;
          color: #8bd9c0;
        }

        .unassignedBox {
          background: #3f1d1d;
          color: #fecaca;
        }

        .explanation {
          color: #d1d5db;
          line-height: 1.6;
        }

        .candidateGrid {
          display: grid;
          grid-template-columns: repeat(3, 1fr);
          gap: 14px;
          margin-top: 14px;
        }

        .candidate {
          border: 1px solid #263244;
          border-radius: 14px;
          padding: 12px;
          background: #0f172a;
        }

        .candidate strong,
        .candidate span,
        .candidate b,
        .candidate small {
          display: block;
        }

        .candidate span {
          color: #9ca3af;
          font-size: 13px;
          margin-top: 4px;
        }

        .candidate b {
          font-size: 24px;
          color: #93c5fd;
          margin: 8px 0;
        }

        .candidate small {
          color: #cbd5e1;
        }

        .error {
          background: #3f1d1d;
          color: #fecaca;
          padding: 12px;
          border-radius: 12px;
        }

        @media (max-width: 900px) {
          .hero,
          .assignmentHeader {
            flex-direction: column;
          }

          .candidateGrid {
            grid-template-columns: 1fr;
          }

          .app {
            padding: 18px;
          }
        }
    """,

    "frontend/src/main.jsx": r"""
        import React from "react";
        import { createRoot } from "react-dom/client";
        import App from "./App.jsx";
        import "./styles.css";

        createRoot(document.getElementById("root")).render(
          <React.StrictMode>
            <App />
          </React.StrictMode>
        );
    """,

    "frontend/src/App.jsx": r"""
        import { useEffect, useState } from "react";

        import { apiGet, apiPost } from "./api/client";
        import AssignmentCard from "./components/AssignmentCard";
        import ResourceTable from "./components/ResourceTable";
        import TaskTable from "./components/TaskTable";

        export default function App() {
          const [resources, setResources] = useState([]);
          const [tasks, setTasks] = useState([]);
          const [result, setResult] = useState(null);
          const [now, setNow] = useState("10:30");
          const [loading, setLoading] = useState(false);
          const [error, setError] = useState("");

          async function loadData() {
            try {
              const [resourceData, taskData] = await Promise.all([
                apiGet("/resources"),
                apiGet("/tasks"),
              ]);

              setResources(resourceData);
              setTasks(taskData);
            } catch (err) {
              setError(err.message);
            }
          }

          async function runAssignment() {
            setLoading(true);
            setError("");

            try {
              const data = await apiPost(`/assign/sample?now_hhmm=${encodeURIComponent(now)}`);
              setResult(data);
            } catch (err) {
              setError(err.message);
            } finally {
              setLoading(false);
            }
          }

          useEffect(() => {
            loadData();
          }, []);

          return (
            <main className="app">
              <section className="hero">
                <div>
                  <h1>AI Task Allocation System</h1>
                  <p>
                    Assign service/support tasks to the most suitable available resource using
                    idle status, shift timing, workload, skill match, experience, and past performance.
                  </p>
                </div>

                <div className="controls">
                  <label>
                    Demo time{" "}
                    <input value={now} onChange={(event) => setNow(event.target.value)} />
                  </label>
                  <button onClick={runAssignment} disabled={loading}>
                    {loading ? "Assigning..." : "Run Assignment"}
                  </button>
                </div>
              </section>

              {error && <div className="error">{error}</div>}

              <section className="grid">
                <ResourceTable resources={resources} />
                <TaskTable tasks={tasks} />

                {result && (
                  <div className="card">
                    <h2>Assignment Result</h2>
                    <p>
                      Assigned {result.assigned_count} of {result.total_tasks} tasks.
                      Unassigned: {result.unassigned_count}.
                    </p>

                    <div className="results">
                      {result.assignments.map((item) => (
                        <AssignmentCard key={item.task.task_id} item={item} />
                      ))}
                    </div>
                  </div>
                )}
              </section>
            </main>
          );
        }
    """,

    "README.md": r"""
        # AI Task Allocation System

        An intelligent workforce assignment system for service/customer-support environments.

        The system receives multiple incoming tasks and assigns each task to the most suitable available resource by checking:

        - idle status
        - shift timing
        - current workload
        - skill match
        - task category
        - past performance
        - experience level
        - average resolution speed

        ## Current Version

        This is the MVP version.

        It uses a transparent rule-based scoring engine first.  
        A trained ML ranking model can be added later using assignment history.

        ## Run Backend

        ```bash
        cd backend
        python -m venv .venv
        .venv\Scripts\activate
        pip install -r requirements.txt
        uvicorn app.main:app --reload --port 8000
        ```

        Open:

        ```txt
        http://127.0.0.1:8000
        http://127.0.0.1:8000/docs
        ```

        ## Run Frontend

        Open a second terminal:

        ```bash
        cd frontend
        npm install
        npm run dev
        ```

        Open the Vite URL shown in the terminal.

        ## Important Endpoints

        ```txt
        GET  /resources
        GET  /tasks
        GET  /history
        POST /assign
        POST /assign/batch
        POST /assign/sample
        ```

        ## Example Assignment Logic

        For every task-resource pair, the backend calculates:

        ```txt
        final_score =
          skill_match * 0.30
        + availability * 0.20
        + workload * 0.15
        + category_match * 0.15
        + past_performance * 0.10
        + experience * 0.05
        + speed * 0.05
        ```

        Resources are rejected before scoring if they are:

        - offline
        - outside shift timing
        - already at max workload
        - missing required skills

        ## Next Upgrade

        Add a trained ranking model using historical data:

        - task type
        - required skills
        - resource assigned
        - workload at assignment time
        - completion time
        - success/failure
        - customer rating
        - escalation status

        Recommended model later:

        ```txt
        LightGBM Ranker or XGBoost Ranker
        ```
    """,
}


def main():
    for path, content in FILES.items():
        write_file(path, content)

    print("\nMVP code generated successfully.")
    print("\nNext steps:")
    print("1. cd backend")
    print("2. python -m venv .venv")
    print("3. .\\.venv\\Scripts\\Activate.ps1")
    print("4. pip install -r requirements.txt")
    print("5. uvicorn app.main:app --reload --port 8000")
    print("6. Open http://127.0.0.1:8000/docs")
    print("7. Open a second terminal")
    print("8. cd frontend")
    print("9. npm install")
    print("10. npm run dev")


if __name__ == "__main__":
    main()
