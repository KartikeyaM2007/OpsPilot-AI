export default function MLPanel({ status, selectedModelType, onModelTypeChange, onTrain, loading }) {
  const metadata = status?.metadata || {};
  const topFeatures = metadata.top_features || [];
  const options = status?.available_model_types || [
    { value: "lightgbm_ranker", label: "LightGBM LGBMRanker", available: true },
    { value: "random_forest", label: "RandomForestClassifier", available: true },
    { value: "random_baseline", label: "Random Baseline", available: true },
  ];

  return (
    <div className="card">
      <h2>Trainable ML Ranker</h2>
      <p className="muted">
        Choose which ML strategy to train/use. LightGBM Ranker is best for this task-allocation ranking problem.
      </p>

      <div className="modelSelector">
        <label>
          ML strategy
          <select
            value={selectedModelType}
            onChange={(event) => onModelTypeChange(event.target.value)}
          >
            {options.map((option) => (
              <option key={option.value} value={option.value} disabled={!option.available}>
                {option.label}{option.available ? "" : " (install dependency)"}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="mlGrid">
        <div>
          <b>{status?.model_exists ? "Ready" : "Not trained"}</b>
          <span>Model status</span>
        </div>
        <div>
          <b>{metadata.model_type || "Not trained yet"}</b>
          <span>Current trained model</span>
        </div>
        <div>
          <b>{status?.training_rows || 0}</b>
          <span>Candidate rows</span>
        </div>
        <div>
          <b>{status?.query_groups || metadata.query_groups || 0}</b>
          <span>Task groups</span>
        </div>
        <div>
          <b>{status?.positive_rows || 0}</b>
          <span>Selected rows</span>
        </div>
        <div>
          <b>{status?.negative_rows || 0}</b>
          <span>Rejected rows</span>
        </div>
        <div>
          <b>{metadata.train_hit_at_1 ?? "-"}</b>
          <span>Train Hit@1</span>
        </div>
        <div>
          <b>{status?.lightgbm_installed ? "Yes" : "No"}</b>
          <span>LightGBM installed</span>
        </div>
      </div>

      {metadata.trained_at && (
        <div className="mlMeta">
          <strong>Last trained</strong>
          <span>{metadata.trained_at}</span>
          <strong>Selected strategy</strong>
          <span>{selectedModelType}</span>
          <strong>Saved model type</strong>
          <span>{metadata.model_type}</span>
          <strong>Ranking metric</strong>
          <span>Hit@1 = {metadata.train_hit_at_1 ?? "-"}</span>
        </div>
      )}

      {topFeatures.length > 0 && (
        <div className="featureList">
          <strong>Top learned features</strong>
          {topFeatures.map((item) => (
            <div key={item.feature}>
              <span>{item.feature.replaceAll("_", " ")}</span>
              <b>{item.importance}</b>
            </div>
          ))}
        </div>
      )}

      <button onClick={() => onTrain(selectedModelType)} disabled={loading}>
        {loading ? "Training..." : `Train ${selectedModelType.replaceAll("_", " ")}`}
      </button>
    </div>
  );
}
