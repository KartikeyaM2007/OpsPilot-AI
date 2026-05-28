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
