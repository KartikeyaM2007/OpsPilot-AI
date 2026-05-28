export default function LLMPanel({ status }) {
  if (!status) return null;

  const ollama = status.providers?.ollama || {};
  const openai = status.providers?.openai || {};
  const gemini = status.providers?.gemini || {};

  return (
    <div className="card llmPanel">
      <div className="dashboardHeader">
        <div>
          <h2>Multi-Provider LLM Layer</h2>
          <p className="muted">
            Used for mock task/resource generation and later for task parsing or explanation. Final assignment still comes from scoring + RAG + ML.
          </p>
        </div>

        <div className={`modelBadge ${ollama.running ? "ready" : "notReady"}`}>
          {ollama.running ? "Ollama Running" : "Ollama Offline"}
        </div>
      </div>

      <div className="llmGrid">
        <div>
          <b>Default</b>
          <span>{status.default_provider}</span>
        </div>
        <div>
          <b>Ollama</b>
          <span>{ollama.model}</span>
          <small>{ollama.base_url}</small>
        </div>
        <div>
          <b>OpenAI</b>
          <span>{openai.configured ? "Configured" : "No API key"}</span>
          <small>{openai.model}</small>
        </div>
        <div>
          <b>Gemini</b>
          <span>{gemini.configured ? "Configured" : "No API key"}</span>
          <small>{gemini.model}</small>
        </div>
      </div>

      {!ollama.running && (
        <p className="warningText">
          Ollama is not reachable. Mock buttons will still work using deterministic fallback data.
        </p>
      )}
    </div>
  );
}
