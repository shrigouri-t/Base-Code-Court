"""Random Forest inference for final contributor scores."""

from functools import lru_cache
import logging
from math import isfinite
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor


logger = logging.getLogger(__name__)

MODEL_FEATURES = (
    "commits_count",
    "lines_added",
    "quality_modifier",
    "adjusted_work",
    "surviving_lines",
    "survival_rate",
    "prs_reviewed",
    "issues_handled",
    "github_data_available",
    "work_score",
    "survival_score",
    "ownership_score",
    "review_score",
    "issues_score",
    "consistency_score",
    "base_score",
    "anomaly_flag",
    "penalty_multiplier",
)

FEATURE_LABELS = {
    "commits_count": "Commit Activity",
    "lines_added": "Meaningful Code Added",
    "quality_modifier": "Code Quality",
    "adjusted_work": "Quality-Adjusted Work",
    "surviving_lines": "Surviving Lines",
    "survival_rate": "Code Longevity",
    "prs_reviewed": "Review Activity",
    "issues_handled": "Issue Activity",
    "github_data_available": "GitHub Data Availability",
    "work_score": "Work Signal",
    "survival_score": "Code Longevity",
    "ownership_score": "Code Ownership",
    "review_score": "Review Activity",
    "issues_score": "Issue Activity",
    "consistency_score": "Consistency",
    "base_score": "Base Score",
    "anomaly_flag": "Anomaly Detected",
    "penalty_multiplier": "Anomaly Penalty",
}


@lru_cache(maxsize=1)
def _load_model() -> tuple[RandomForestRegressor, Any | None]:
    model_path = Path(__file__).resolve().parents[2] / "models" / "code_court_v1.1.pkl"
    model = joblib.load(model_path)
    if not isinstance(model, RandomForestRegressor):
        raise TypeError(f"expected a RandomForestRegressor in {model_path}")
    model_features = getattr(model, "feature_names_in_", None)
    if model_features is None or tuple(model_features) != MODEL_FEATURES:
        raise ValueError(f"model features do not match the expected contract in {model_path}")
    try:
        import shap

        explainer = shap.TreeExplainer(model)
    except ImportError:
        logger.info("SHAP is not installed; native tree-path attribution will be used")
        explainer = None
    except Exception:
        logger.warning(
            "Unable to initialize SHAP TreeExplainer; native tree-path attribution will be used",
            exc_info=True,
        )
        explainer = None
    return model, explainer


def _feature_frame(feature_rows: list[dict[str, float]]) -> pd.DataFrame:
    for row in feature_rows:
        if set(row) != set(MODEL_FEATURES):
            raise ValueError("model input fields do not match the expected feature contract")
    return pd.DataFrame(
        [{name: row[name] for name in MODEL_FEATURES} for row in feature_rows],
        columns=MODEL_FEATURES,
    )


def predict_final_scores(feature_rows: list[dict[str, float]]) -> list[float]:
    """Predict normalized model targets and return report scores in the 0..100 scale."""
    if not feature_rows:
        return []
    frame = _feature_frame(feature_rows)
    model, _ = _load_model()
    predictions = model.predict(frame)
    if len(predictions) != len(feature_rows):
        raise ValueError("model returned an unexpected number of scores")

    scores = []
    for prediction in predictions:
        normalized_score = float(prediction)
        if not isfinite(normalized_score) or not 0.0 <= normalized_score <= 1.0:
            raise ValueError("model prediction must be a finite value between 0 and 1")
        scores.append(round(normalized_score * 100, 2))
    return scores


def _shap_attributions(explainer: Any, frame: pd.DataFrame) -> np.ndarray:
    values = explainer.shap_values(frame)
    if isinstance(values, list):
        if len(values) != 1:
            raise ValueError("expected one SHAP output for the regression model")
        values = values[0]
    values = getattr(values, "values", values)
    matrix = np.asarray(values, dtype=float)
    if matrix.ndim == 3 and matrix.shape[-1] == 1:
        matrix = matrix[:, :, 0]
    if matrix.shape != (len(frame), len(MODEL_FEATURES)):
        raise ValueError("SHAP returned an unexpected attribution shape")
    if not np.isfinite(matrix).all():
        raise ValueError("SHAP returned a non-finite attribution")
    return matrix


def _tree_path_attributions(
    model: RandomForestRegressor,
    frame: pd.DataFrame,
) -> np.ndarray:
    """Decompose each forest prediction along the decision paths of its trees."""
    estimators = getattr(model, "estimators_", None)
    if not estimators:
        raise ValueError("random forest has no fitted trees")

    attributions = np.zeros((len(frame), len(MODEL_FEATURES)), dtype=float)
    for row_index, row in enumerate(frame.to_numpy(dtype=float)):
        for estimator in estimators:
            tree = estimator.tree_
            node = 0
            while tree.children_left[node] != tree.children_right[node]:
                feature_index = int(tree.feature[node])
                if not 0 <= feature_index < len(MODEL_FEATURES):
                    raise ValueError("tree contains an invalid feature index")
                child = (
                    tree.children_left[node]
                    if row[feature_index] <= tree.threshold[node]
                    else tree.children_right[node]
                )
                attributions[row_index, feature_index] += (
                    tree.value[child, 0, 0] - tree.value[node, 0, 0]
                )
                node = child
        attributions[row_index] /= len(estimators)

    if not np.isfinite(attributions).all():
        raise ValueError("tree-path attribution returned a non-finite value")
    return attributions


def _format_feature_impacts(attributions: np.ndarray) -> list[list[dict[str, Any]]]:
    result = []
    for row in attributions:
        impacts = [
            {
                "feature": feature,
                "label": FEATURE_LABELS[feature],
                "impact": round(float(impact) * 100, 2),
            }
            for feature, impact in zip(MODEL_FEATURES, row)
        ]
        impacts.sort(
            key=lambda item: (
                -abs(item["impact"]),
                MODEL_FEATURES.index(item["feature"]),
            )
        )
        result.append(impacts[:6])
    return result


def predict_feature_impacts(
    feature_rows: list[dict[str, float]],
) -> list[list[dict[str, Any]] | None]:
    """Return the largest signed score contributions, or None if unavailable."""
    if not feature_rows:
        return []
    frame = _feature_frame(feature_rows)
    try:
        model, explainer = _load_model()
    except Exception:
        logger.exception("Unable to load model for feature attribution")
        return [None] * len(feature_rows)

    attributions = None
    if explainer is not None:
        try:
            attributions = _shap_attributions(explainer, frame)
        except Exception:
            logger.warning(
                "SHAP attribution failed; using native tree-path attribution",
                exc_info=True,
            )
    if attributions is None:
        try:
            attributions = _tree_path_attributions(model, frame)
        except Exception:
            logger.exception("Unable to compute feature attribution")
            return [None] * len(feature_rows)

    return _format_feature_impacts(attributions)
