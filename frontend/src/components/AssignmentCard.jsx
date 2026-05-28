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

function modeLabel(mode) {
  if (mode === "agentic_rag") return "Agentic RAG mode";
  if (mode === "ml_ranker") return "ML Ranker mode";
  if (mode === "ml_ranker_fallback") return "ML Fallback mode";
  return "";
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
            {item.mode ? ` • ${modeLabel(item.mode)}` : ""}
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
            {item.assigned_resource.ml_probability !== undefined && (
              <small>
                ML probability {Math.round(item.assigned_resource.ml_probability * 100)}%
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
            {candidate.ml_probability !== undefined && (
              <small>
                ML prob: {Math.round(candidate.ml_probability * 100)}%
                {candidate.ml_score !== undefined ? ` | ML score: ${candidate.ml_score}` : ""}
              </small>
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
