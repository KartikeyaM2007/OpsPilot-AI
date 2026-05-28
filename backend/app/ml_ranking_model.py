import json
import random
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

import joblib
import pandas as pd

try:
    from lightgbm import LGBMRanker
except Exception:
    LGBMRanker = None

from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score

from .database import append_ml_training_rows, load_ml_training_rows


DATA_DIR = Path(__file__).resolve().parents[2] / "data"
MODEL_DIR = DATA_DIR / "models"
MODEL_PATH = MODEL_DIR / "assignment_ranker.joblib"
METADATA_PATH = MODEL_DIR / "assignment_ranker_metadata.json"

MODEL_OPTIONS = {
    "lightgbm_ranker": "LightGBM LGBMRanker",
    "random_forest": "RandomForestClassifier",
    "random_baseline": "Random Baseline",
}

FEATURE_COLUMNS = [
    "priority_value", "eligible", "base_score", "rag_bonus",
    "deterministic_score", "skill_match", "availability", "workload",
    "category_match", "past_performance", "experience", "speed",
    "rejection_count",
]

PRIORITY_VALUE = {
    "urgent": 4,
    "high": 3,
    "medium": 2,
    "low": 1,
}


def normalize_model_type(model_type: Optional[str]) -> str:
    value = str(model_type or "lightgbm_ranker").lower().strip()

    aliases = {
        "light": "lightgbm_ranker",
        "lgbm": "lightgbm_ranker",
        "lightgbm": "lightgbm_ranker",
        "ranker": "lightgbm_ranker",
        "rf": "random_forest",
        "randomforest": "random_forest",
        "random_forest_classifier": "random_forest",
        "random": "random_baseline",
        "random_baseline": "random_baseline",
        "baseline": "random_baseline",
    }

    return aliases.get(value, value if value in MODEL_OPTIONS else "lightgbm_ranker")


def _priority_value(priority: str) -> int:
    return PRIORITY_VALUE.get(str(priority).lower(), 2)


def _safe_float(value, default=0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _candidate_to_features(task: Dict, candidate: Dict) -> Dict:
    breakdown = candidate.get("breakdown", {}) or {}

    return {
        "priority_value": _priority_value(task.get("priority")),
        "eligible": 1 if candidate.get("eligible") else 0,
        "base_score": _safe_float(candidate.get("base_score", candidate.get("final_score"))),
        "rag_bonus": _safe_float(candidate.get("rag_bonus")),
        "deterministic_score": _safe_float(candidate.get("base_rag_score", candidate.get("final_score"))),
        "skill_match": _safe_float(breakdown.get("skill_match")),
        "availability": _safe_float(breakdown.get("availability")),
        "workload": _safe_float(breakdown.get("workload")),
        "category_match": _safe_float(breakdown.get("category_match")),
        "past_performance": _safe_float(breakdown.get("past_performance")),
        "experience": _safe_float(breakdown.get("experience")),
        "speed": _safe_float(breakdown.get("speed")),
        "rejection_count": len(candidate.get("rejection_reasons", []) or []),
    }


def append_candidate_training_rows(result: Dict) -> int:
    if not result.get("assigned") or not result.get("assigned_resource"):
        return 0

    candidates = result.get("candidates", []) or []
    if not candidates:
        return 0

    task = result.get("task", {}) or {}
    assigned_resource_id = result.get("assigned_resource", {}).get("resource_id")
    assigned_resource_name = result.get("assigned_resource", {}).get("name")

    query_id = (
        f"{datetime.now().strftime('%Y%m%d%H%M%S%f')}|"
        f"{task.get('title', '')}|{task.get('category', '')}|{task.get('priority', '')}"
    )

    rows = []

    for candidate in candidates:
        features = _candidate_to_features(task, candidate)
        label = int(
            candidate.get("resource_id") == assigned_resource_id
            or candidate.get("resource_name") == assigned_resource_name
        )

        rows.append({
            "row_id": datetime.now().strftime("%Y%m%d%H%M%S%f") + str(len(rows)),
            "query_id": query_id,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "mode": result.get("mode", "normal_scoring"),
            "task_title": task.get("title", ""),
            "task_category": task.get("category", ""),
            "task_priority": task.get("priority", ""),
            "candidate_resource_id": candidate.get("resource_id", ""),
            "candidate_resource_name": candidate.get("resource_name", ""),
            **features,
            "label_selected": label,
        })

    return append_ml_training_rows(rows)


def _load_training_frame() -> pd.DataFrame:
    rows = load_ml_training_rows()
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)

    if "query_id" not in df.columns:
        df["query_id"] = (
            df.get("timestamp", "").astype(str) + "|"
            + df.get("task_title", "").astype(str) + "|"
            + df.get("task_category", "").astype(str) + "|"
            + df.get("task_priority", "").astype(str)
        )

    df["label_selected"] = pd.to_numeric(df["label_selected"], errors="coerce").fillna(0).astype(int)

    for column in FEATURE_COLUMNS:
        if column not in df.columns:
            df[column] = 0
        df[column] = pd.to_numeric(df[column], errors="coerce").fillna(0)

    df = df.sort_values(["query_id", "row_id"]).reset_index(drop=True)
    return df


def _ranking_hit_at_1(df: pd.DataFrame, scores) -> float:
    temp = df[["query_id", "label_selected"]].copy()
    temp["score"] = scores

    hits = 0
    groups = 0

    for _, group in temp.groupby("query_id", sort=False):
        groups += 1
        best = group.sort_values("score", ascending=False).iloc[0]
        if int(best["label_selected"]) == 1:
            hits += 1

    return round(hits / max(groups, 1), 4)


def _group_sizes(df: pd.DataFrame) -> list:
    return df.groupby("query_id", sort=False).size().astype(int).tolist()


def _read_metadata() -> Dict:
    if METADATA_PATH.exists():
        return json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    return {}


def get_ml_status() -> Dict:
    df = _load_training_frame()
    training_rows = len(df)
    positive_rows = int((df["label_selected"] == 1).sum()) if training_rows else 0
    negative_rows = training_rows - positive_rows
    query_groups = int(df["query_id"].nunique()) if training_rows else 0
    metadata = _read_metadata()

    return {
        "model_exists": MODEL_PATH.exists(),
        "training_file_exists": training_rows > 0,
        "training_rows": training_rows,
        "positive_rows": positive_rows,
        "negative_rows": negative_rows,
        "query_groups": query_groups,
        "model_path": str(MODEL_PATH),
        "metadata": metadata,
        "storage": "sqlite",
        "available_model_types": [
            {
                "value": key,
                "label": label,
                "available": key != "lightgbm_ranker" or LGBMRanker is not None,
            }
            for key, label in MODEL_OPTIONS.items()
        ],
        "lightgbm_installed": LGBMRanker is not None,
    }


def _validate_training_data(df: pd.DataFrame, model_type: str) -> Optional[str]:
    if df.empty:
        return "No candidate training data found yet. Run a few assignments first."

    if len(df) < 4:
        return "Not enough candidate rows yet. Run a few more assignments."

    if df["label_selected"].nunique() < 2:
        return "Training data needs both selected and non-selected candidates."

    if model_type == "lightgbm_ranker" and int(df["query_id"].nunique()) < 2:
        return "Training data needs at least 2 task groups for ranking."

    return None


def _train_random_forest(df: pd.DataFrame) -> Dict:
    X = df[FEATURE_COLUMNS].fillna(0)
    y = df["label_selected"].astype(int)

    model = RandomForestClassifier(
        n_estimators=160,
        max_depth=8,
        random_state=42,
        class_weight="balanced",
    )
    model.fit(X, y)

    predictions = model.predict(X)
    scores = model.predict_proba(X)[:, 1] if hasattr(model, "predict_proba") else predictions
    train_accuracy = float(accuracy_score(y, predictions))
    hit_at_1 = _ranking_hit_at_1(df, scores)

    importances = sorted(
        zip(FEATURE_COLUMNS, model.feature_importances_),
        key=lambda item: item[1],
        reverse=True,
    )

    return {
        "model": model,
        "model_type": "RandomForestClassifier",
        "train_accuracy": round(train_accuracy, 4),
        "train_hit_at_1": hit_at_1,
        "top_features": [
            {"feature": feature, "importance": round(float(value), 4)}
            for feature, value in importances[:8]
        ],
    }


def _train_lgbm_ranker(df: pd.DataFrame) -> Dict:
    X = df[FEATURE_COLUMNS].fillna(0)
    y = df["label_selected"].astype(int)
    groups = _group_sizes(df)

    model = LGBMRanker(
        objective="lambdarank",
        metric="ndcg",
        n_estimators=180,
        learning_rate=0.05,
        num_leaves=15,
        max_depth=-1,
        random_state=42,
        verbose=-1,
    )

    model.fit(X, y, group=groups)

    scores = model.predict(X)
    hit_at_1 = _ranking_hit_at_1(df, scores)

    importances = sorted(
        zip(FEATURE_COLUMNS, model.feature_importances_),
        key=lambda item: item[1],
        reverse=True,
    )

    return {
        "model": model,
        "model_type": "LightGBM LGBMRanker",
        "train_accuracy": None,
        "train_hit_at_1": hit_at_1,
        "top_features": [
            {"feature": feature, "importance": round(float(value), 4)}
            for feature, value in importances[:8]
        ],
    }


def _train_random_baseline(df: pd.DataFrame) -> Dict:
    random.seed(42)
    scores = [random.random() for _ in range(len(df))]
    hit_at_1 = _ranking_hit_at_1(df, scores)

    return {
        "model": {
            "kind": "random_baseline",
            "seed": 42,
        },
        "model_type": "Random Baseline",
        "train_accuracy": None,
        "train_hit_at_1": hit_at_1,
        "top_features": [],
    }


def train_ml_model(model_type: Optional[str] = None) -> Dict:
    selected_model_type = normalize_model_type(model_type)
    df = _load_training_frame()

    validation_error = _validate_training_data(df, selected_model_type)
    if validation_error:
        return {
            "trained": False,
            "message": validation_error,
            "status": get_ml_status(),
        }

    if selected_model_type == "lightgbm_ranker":
        if LGBMRanker is None:
            return {
                "trained": False,
                "message": "LightGBM is not installed. Run: pip install lightgbm",
                "status": get_ml_status(),
            }
        train_result = _train_lgbm_ranker(df)
    elif selected_model_type == "random_forest":
        train_result = _train_random_forest(df)
    else:
        train_result = _train_random_baseline(df)

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump({
        "model": train_result["model"],
        "model_type": train_result["model_type"],
        "requested_model_type": selected_model_type,
        "feature_columns": FEATURE_COLUMNS,
    }, MODEL_PATH)

    metadata = {
        "trained_at": datetime.now().isoformat(timespec="seconds"),
        "training_rows": int(len(df)),
        "query_groups": int(df["query_id"].nunique()),
        "positive_rows": int((df["label_selected"] == 1).sum()),
        "negative_rows": int((df["label_selected"] == 0).sum()),
        "requested_model_type": selected_model_type,
        "model_type": train_result["model_type"],
        "train_accuracy": train_result["train_accuracy"],
        "train_hit_at_1": train_result["train_hit_at_1"],
        "storage": "sqlite",
        "top_features": train_result["top_features"],
    }

    METADATA_PATH.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    return {
        "trained": True,
        "message": f"{train_result['model_type']} trained successfully.",
        "metadata": metadata,
        "status": get_ml_status(),
    }


def _load_model_bundle():
    if not MODEL_PATH.exists():
        return None

    loaded = joblib.load(MODEL_PATH)

    if isinstance(loaded, dict) and "model" in loaded:
        return loaded

    return {
        "model": loaded,
        "model_type": "LegacyModel",
        "requested_model_type": "legacy",
        "feature_columns": FEATURE_COLUMNS,
    }


def _predict_candidate_score(model_bundle: Dict, task: Dict, candidate: Dict) -> float:
    model = model_bundle["model"]
    model_type = model_bundle.get("model_type", "")
    feature_columns = model_bundle.get("feature_columns", FEATURE_COLUMNS)

    if model_type == "Random Baseline" or isinstance(model, dict) and model.get("kind") == "random_baseline":
        key = f"{task.get('title', '')}|{candidate.get('resource_id', '')}|{candidate.get('resource_name', '')}"
        return random.Random(key).random()

    features = _candidate_to_features(task, candidate)
    X = pd.DataFrame([{column: features.get(column, 0) for column in feature_columns}])

    if "Ranker" in model_type or hasattr(model, "booster_"):
        return float(model.predict(X)[0])

    if hasattr(model, "predict_proba"):
        return float(model.predict_proba(X)[0][1])

    return float(model.predict(X)[0])


def _append_ml_workflow_step(result: Dict, model_available: bool, winner: Optional[Dict], model_type: str = "") -> None:
    trace = result.get("workflow_trace") or []

    trace.append({
        "name": "ML Ranker",
        "status": "completed" if model_available else "fallback",
        "detail": (
            f"{model_type} re-ranked eligible candidates using candidate-level training history from SQLite."
            if model_available
            else "No trained ML model found, so the system used Agentic RAG scoring as fallback."
        ),
        "data": {
            "model_available": model_available,
            "model_type": model_type,
            "selected_by_ml": winner.get("resource_name") if winner else None,
            "ml_score": winner.get("ml_score") if winner else None,
        },
    })

    result["workflow_trace"] = trace


def assign_task_ml(task: Dict, now_hhmm: Optional[str] = None, model_type: Optional[str] = None) -> Dict:
    from .agentic_assignment_engine import assign_task_agentic

    result = assign_task_agentic(task, now_hhmm=now_hhmm)
    model_bundle = _load_model_bundle()

    if model_bundle is None or not result.get("assigned"):
        result["mode"] = "ml_ranker_fallback"
        result["explanation"] = (
            result.get("explanation", "")
            + " ML ranker fallback was used because no trained model is available yet."
        ).strip()
        _append_ml_workflow_step(result, False, None)
        return result

    requested = normalize_model_type(model_type)
    trained_requested = model_bundle.get("requested_model_type")

    if model_type and trained_requested and requested != trained_requested:
        # Runtime uses the currently trained model file. Frontend should train selected type first.
        result["model_warning"] = (
            f"Requested {requested}, but currently trained model is {trained_requested}. "
            f"Train {requested} first to switch."
        )

    task_data = result.get("task", {}) or {}
    candidates = result.get("candidates", []) or []
    actual_model_type = model_bundle.get("model_type", "MLRanker")

    raw_scores = []

    for candidate in candidates:
        candidate["base_rag_score"] = candidate.get("final_score", 0)

        if candidate.get("eligible"):
            raw_score = _predict_candidate_score(model_bundle, task_data, candidate)
            candidate["ml_raw_score"] = round(raw_score, 4)
            raw_scores.append(raw_score)
        else:
            candidate["ml_raw_score"] = 0.0

    eligible_raw_scores = [candidate["ml_raw_score"] for candidate in candidates if candidate.get("eligible")]
    min_score = min(eligible_raw_scores) if eligible_raw_scores else 0
    max_score = max(eligible_raw_scores) if eligible_raw_scores else 1
    score_range = max(max_score - min_score, 1e-9)

    for candidate in candidates:
        if candidate.get("eligible"):
            normalized_score = (candidate["ml_raw_score"] - min_score) / score_range
            candidate["ml_probability"] = round(normalized_score, 4)
            candidate["ml_score"] = round((normalized_score * 100 * 0.65) + (candidate["base_rag_score"] * 0.35), 2)
            candidate["final_score"] = candidate["ml_score"]
            candidate["positive_reasons"] = candidate.get("positive_reasons", []) + [
                f"{actual_model_type} normalized rank score {round(normalized_score * 100, 2)}%"
            ]
        else:
            candidate["ml_probability"] = 0.0
            candidate["ml_score"] = 0.0

    candidates.sort(key=lambda item: item.get("final_score", 0), reverse=True)
    valid_candidates = [candidate for candidate in candidates if candidate.get("eligible")]

    if not valid_candidates:
        result["mode"] = "ml_ranker"
        result["assigned"] = False
        result["assigned_resource"] = None
        _append_ml_workflow_step(result, True, None, model_type=actual_model_type)
        return result

    winner = valid_candidates[0]

    result["mode"] = "ml_ranker"
    result["candidates"] = candidates
    result["assigned"] = True
    result["assigned_resource"] = {
        "resource_id": winner["resource_id"],
        "name": winner["resource_name"],
        "score": winner["final_score"],
        "base_score": winner.get("base_score"),
        "rag_bonus": winner.get("rag_bonus"),
        "ml_probability": winner.get("ml_probability"),
        "ml_score": winner.get("ml_score"),
        "ml_raw_score": winner.get("ml_raw_score"),
        "model_type": actual_model_type,
    }

    warning_text = f" Warning: {result.get('model_warning')}" if result.get("model_warning") else ""

    result["explanation"] = (
        f"{actual_model_type} assigned this task to {winner.get('resource_name')} after using "
        f"Agentic RAG evidence plus the selected ML model. "
        f"The selected candidate received normalized ML rank score "
        f"{round(winner.get('ml_probability', 0) * 100, 2)}% and blended score "
        f"{winner.get('ml_score')}. "
        f"{warning_text} "
        f"Original explanation: {result.get('explanation', '')}"
    )

    _append_ml_workflow_step(result, True, winner, model_type=actual_model_type)
    return result
