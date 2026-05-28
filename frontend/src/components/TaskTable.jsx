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
