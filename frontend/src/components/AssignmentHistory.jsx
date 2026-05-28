export default function AssignmentHistory({ logs }) {
  return (
    <div className="card">
      <h2>Assignment History</h2>
      <p className="muted">
        Every normal and Agentic RAG assignment is logged here. This becomes training data for the future ML ranking model.
      </p>

      {logs.length === 0 ? (
        <div className="emptyState">
          No assignments logged yet. Run Normal Assignment or Agentic RAG Assignment first.
        </div>
      ) : (
        <div className="historyList">
          {logs.map((log) => (
            <div className="historyItem" key={log.log_id}>
              <div className="historyTop">
                <div>
                  <strong>{log.task_title}</strong>
                  <span>
                    {log.task_category} • {log.task_priority} • {log.mode}
                  </span>
                </div>

                <div className="historyScore">
                  <b>{log.assigned_resource || "Unassigned"}</b>
                  <span>{log.score ? `Score ${log.score}` : "No score"}</span>
                </div>
              </div>

              <p>{log.explanation}</p>

              <div className="historyMeta">
                <span>{log.timestamp}</span>
                <span>Skills: {log.required_skills}</span>
                {log.rag_bonus && <span>RAG bonus: {log.rag_bonus}</span>}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
