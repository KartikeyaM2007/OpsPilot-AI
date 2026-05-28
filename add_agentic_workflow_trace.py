from pathlib import Path

ROOT = Path(__file__).resolve().parent

def write_file(relative_path: str, content: str):
    path = ROOT / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.strip() + "\n", encoding="utf-8")
    print(f"updated: {relative_path}")

write_file("backend/app/agentic_assignment_engine.py", r"""
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
""")

write_file("frontend/src/components/WorkflowTrace.jsx", r"""
function formatValue(value) {
  if (Array.isArray(value)) {
    return value.join(", ");
  }

  if (value && typeof value === "object") {
    return JSON.stringify(value);
  }

  return String(value);
}

export default function WorkflowTrace({ trace }) {
  if (!trace || trace.length === 0) return null;

  return (
    <div className="workflowBox">
      <h4>Agentic Workflow Trace</h4>
      <div className="workflowSteps">
        {trace.map((step, index) => (
          <div className="workflowStep" key={`${step.name}-${index}`}>
            <div className="stepIndex">{index + 1}</div>

            <div className="stepContent">
              <div className="stepTop">
                <strong>{step.name}</strong>
                <span className={`stepStatus ${step.status}`}>{step.status}</span>
              </div>

              <p>{step.detail}</p>

              {step.data && Object.keys(step.data).length > 0 && (
                <div className="stepData">
                  {Object.entries(step.data).slice(0, 4).map(([key, value]) => (
                    <div key={key}>
                      <b>{key.replaceAll("_", " ")}</b>
                      <span>{formatValue(value)}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
""")

write_file("frontend/src/components/AssignmentCard.jsx", r"""
import WorkflowTrace from "./WorkflowTrace";

function RagContext({ context }) {
  if (!context) return null;

  const similarCases = context.similar_cases || [];
  const policies = context.policy_context || [];

  return (
    <div className="ragBox">
      <h4>Agentic RAG Evidence</h4>

      {similarCases.length > 0 && (
        <>
          <strong>Similar past cases</strong>
          <div className="ragCases">
            {similarCases.slice(0, 3).map((item) => (
              <div className="ragCase" key={item.case_id}>
                <b>{item.title}</b>
                <span>
                  Agent: {item.resource_name} • Similarity: {item.similarity_score} •
                  Success: {item.success} • Escalated: {item.escalated}
                </span>
              </div>
            ))}
          </div>
        </>
      )}

      {policies.length > 0 && (
        <>
          <strong>Retrieved SOP / policy context</strong>
          <ul>
            {policies.slice(0, 2).map((policy, index) => (
              <li key={index}>{policy}</li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}

export default function AssignmentCard({ item }) {
  const topCandidates = item.candidates?.slice(0, 3) || [];

  return (
    <div className="assignmentCard">
      <div className="assignmentHeader">
        <div>
          <h3>{item.task.title}</h3>
          <p>
            {item.task.category} • {item.task.priority}
            {item.mode === "agentic_rag" ? " • Agentic RAG mode" : ""}
          </p>
        </div>

        {item.assigned ? (
          <div className="assignedBox">
            <span>Assigned to</span>
            <strong>{item.assigned_resource.name}</strong>
            <small>Score {item.assigned_resource.score}</small>
            {item.assigned_resource.rag_bonus !== undefined && (
              <small>
                Base {item.assigned_resource.base_score} + RAG {item.assigned_resource.rag_bonus}
              </small>
            )}
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
            {candidate.rag_bonus !== undefined && (
              <small>Base: {candidate.base_score} | RAG: {candidate.rag_bonus}</small>
            )}
            <small>
              {candidate.eligible
                ? candidate.positive_reasons?.slice(0, 2).join(", ")
                : candidate.rejection_reasons?.slice(0, 2).join(", ")}
            </small>
          </div>
        ))}
      </div>

      <WorkflowTrace trace={item.workflow_trace} />
      <RagContext context={item.rag_context} />
    </div>
  );
}
""")

css_path = ROOT / "frontend/src/styles.css"
extra_css = r"""

.workflowBox {
  margin-top: 16px;
  border: 1px solid #334155;
  border-radius: 14px;
  padding: 14px;
  background: #0f172a;
}

.workflowBox h4 {
  margin: 0 0 14px;
  color: #93c5fd;
}

.workflowSteps {
  display: grid;
  gap: 12px;
}

.workflowStep {
  display: grid;
  grid-template-columns: 34px 1fr;
  gap: 12px;
  align-items: start;
}

.stepIndex {
  width: 30px;
  height: 30px;
  border-radius: 999px;
  display: grid;
  place-items: center;
  background: #1d4ed8;
  color: white;
  font-weight: 900;
}

.stepContent {
  border: 1px solid #263244;
  border-radius: 12px;
  padding: 12px;
  background: #111827;
}

.stepTop {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
}

.stepTop strong {
  color: #dbeafe;
}

.stepStatus {
  border-radius: 999px;
  padding: 4px 8px;
  font-size: 12px;
  text-transform: capitalize;
  background: #334155;
  color: #e5e7eb;
}

.stepStatus.completed {
  background: #064e3b;
  color: #a7f3d0;
}

.stepStatus.blocked {
  background: #7f1d1d;
  color: #fecaca;
}

.stepContent p {
  margin: 8px 0 0;
  color: #cbd5e1;
  line-height: 1.5;
}

.stepData {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px;
  margin-top: 10px;
}

.stepData div {
  border-radius: 10px;
  padding: 8px;
  background: #0b1222;
}

.stepData b,
.stepData span {
  display: block;
}

.stepData b {
  color: #93c5fd;
  font-size: 12px;
  text-transform: capitalize;
}

.stepData span {
  color: #e5e7eb;
  margin-top: 4px;
  word-break: break-word;
}

@media (max-width: 900px) {
  .stepData {
    grid-template-columns: 1fr;
  }
}
"""

if css_path.exists():
    current_css = css_path.read_text(encoding="utf-8")
    if ".workflowBox" not in current_css:
        css_path.write_text(current_css.rstrip() + extra_css + "\n", encoding="utf-8")
        print("updated: frontend/src/styles.css")
    else:
        print("skipped: frontend/src/styles.css already has workflow styles")

readme = ROOT / "README.md"
if readme.exists():
    current = readme.read_text(encoding="utf-8")
    section = r"""

## Agentic Workflow Trace

The Agentic RAG endpoint now returns a workflow trace:

```txt
Task Intake
→ Task Parser Agent
→ RAG Retriever
→ Resource State Checker
→ Scoring Engine
→ RAG Score Adjuster
→ Assignment Decision
→ Explanation Generator
```

The frontend shows this trace under each Agentic RAG result, making the decision pipeline visible and explainable.
"""
    if "## Agentic Workflow Trace" not in current:
        readme.write_text(current.rstrip() + section + "\n", encoding="utf-8")
        print("updated: README.md")

print("\nAgentic workflow trace upgrade added successfully.")
print("Backend should auto-reload. Frontend should hot-refresh.")
print("Run Agentic RAG Assignment again to see the workflow trace.")
