export default function ResourceTable({ resources, onDelete }) {
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
              {onDelete && <th>Action</th>}
            </tr>
          </thead>
          <tbody>
            {resources.map((resource) => (
              <tr key={resource.resource_id}>
                <td>
                  <strong>{resource.name}</strong>
                  <div className="muted">{resource.resource_id}</div>
                </td>
                <td>
                  <span className={`pill ${resource.status}`}>{resource.status}</span>
                </td>
                <td>{resource.current_tasks}/{resource.max_tasks}</td>
                <td>{resource.shift_start} - {resource.shift_end}</td>
                <td>{resource.skills?.join(", ")}</td>
                <td>{Math.round(Number(resource.success_rate) * 100)}%</td>
                {onDelete && (
                  <td>
                    <button
                      className="miniDanger"
                      onClick={() => onDelete(resource.resource_id)}
                    >
                      Delete
                    </button>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
