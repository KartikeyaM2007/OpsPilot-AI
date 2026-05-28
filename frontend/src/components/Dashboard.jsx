function StatCard({ label, value, hint }) {
  return (
    <div className="statCard">
      <b>{value}</b>
      <span>{label}</span>
      {hint && <small>{hint}</small>}
    </div>
  );
}

function BarList({ title, items }) {
  const maxValue = Math.max(...items.map((item) => Number(item.value) || 0), 1);

  return (
    <div className="dashPanel">
      <h3>{title}</h3>

      {items.length === 0 ? (
        <p className="muted">No data yet.</p>
      ) : (
        <div className="barList">
          {items.map((item) => {
            const width = Math.round((Number(item.value) / maxValue) * 100);

            return (
              <div className="barItem" key={item.label}>
                <div className="barTop">
                  <span>{item.label}</span>
                  <b>{item.value}</b>
                </div>
                <div className="barTrack">
                  <div className="barFill" style={{ width: `${width}%` }} />
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function WorkloadPanel({ resources }) {
  return (
    <div className="dashPanel">
      <h3>Resource Workload</h3>

      <div className="barList">
        {resources.map((resource) => (
          <div className="barItem" key={resource.name}>
            <div className="barTop">
              <span>
                {resource.name}{" "}
                <small className={`tinyStatus ${resource.status}`}>{resource.status}</small>
              </span>
              <b>
                {resource.current_tasks}/{resource.max_tasks}
              </b>
            </div>
            <div className="barTrack">
              <div className="barFill" style={{ width: `${resource.workload_percent}%` }} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function Dashboard({ analytics }) {
  if (!analytics) return null;

  const summary = analytics.summary || {};
  const mlMetadata = analytics.ml_status?.metadata || {};

  return (
    <div className="card dashboardCard">
      <div className="dashboardHeader">
        <div>
          <h2>Analytics Dashboard</h2>
          <p className="muted">
            Live overview of workforce capacity, assignment distribution, RAG/ML usage, and model readiness.
          </p>
        </div>

        <div className={`modelBadge ${summary.ml_model_ready ? "ready" : "notReady"}`}>
          {summary.ml_model_ready ? "ML Model Ready" : "ML Model Not Trained"}
        </div>
      </div>

      <div className="statGrid">
        <StatCard label="Resources" value={summary.total_resources || 0} />
        <StatCard label="Idle" value={summary.idle_resources || 0} />
        <StatCard label="Busy" value={summary.busy_resources || 0} />
        <StatCard label="Offline" value={summary.offline_resources || 0} />
        <StatCard label="Assignments" value={summary.total_assignments || 0} />
        <StatCard label="Avg Score" value={summary.avg_assignment_score || 0} />
        <StatCard
          label="Capacity Used"
          value={`${summary.workload_percent || 0}%`}
          hint={`${summary.used_capacity || 0}/${summary.total_capacity || 0} slots`}
        />
        <StatCard label="ML Rows" value={summary.ml_training_rows || 0} />
      </div>

      {mlMetadata.top_features?.length > 0 && (
        <div className="dashPanel wide">
          <h3>Top ML Features</h3>
          <div className="featurePills">
            {mlMetadata.top_features.slice(0, 8).map((item) => (
              <span key={item.feature}>
                {item.feature.replaceAll("_", " ")}: <b>{item.importance}</b>
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="dashboardGrid">
        <WorkloadPanel resources={analytics.resource_workload || []} />
        <BarList title="Assignments by Resource" items={analytics.assignment_distribution || []} />
        <BarList title="Assignments by Category" items={analytics.category_distribution || []} />
        <BarList title="Assignments by Mode" items={analytics.mode_distribution || []} />
        <BarList title="Assignments by Priority" items={analytics.priority_distribution || []} />
      </div>
    </div>
  );
}
