"""Tests for model feature attribution."""

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor

from app.core import ml_scoring


def _feature_row():
    return {feature: 0.0 for feature in ml_scoring.MODEL_FEATURES}


def test_feature_impacts_are_labeled_sorted_and_limited(monkeypatch):
    row = _feature_row()
    row.update({
        "work_score": 0.142,
        "survival_score": 0.085,
        "consistency_score": -0.031,
        "penalty_multiplier": -0.12,
    })

    class Explainer:
        def shap_values(self, _frame):
            return np.array([[row[name] for name in ml_scoring.MODEL_FEATURES]])

    monkeypatch.setattr(
        ml_scoring,
        "_load_model",
        lambda: (object(), Explainer()),
    )

    impacts = ml_scoring.predict_feature_impacts([row])

    assert [item["feature"] for item in impacts[0][:4]] == [
        "work_score",
        "penalty_multiplier",
        "survival_score",
        "consistency_score",
    ]
    assert [item["label"] for item in impacts[0][:4]] == [
        "Work Signal",
        "Anomaly Penalty",
        "Code Longevity",
        "Consistency",
    ]
    assert [item["impact"] for item in impacts[0][:4]] == [
        14.2,
        -12.0,
        8.5,
        -3.1,
    ]
    assert len(impacts[0]) == 6


def test_tree_path_attributions_sum_to_prediction_minus_tree_baseline():
    rows = []
    targets = []
    for value in range(8):
        row = _feature_row()
        row["lines_added"] = float(value)
        rows.append(row)
        targets.append(value / 10)
    frame = pd.DataFrame(rows, columns=ml_scoring.MODEL_FEATURES)
    model = RandomForestRegressor(
        n_estimators=5,
        max_depth=3,
        random_state=3,
    ).fit(frame, targets)

    attributions = ml_scoring._tree_path_attributions(model, frame.iloc[[5]])
    baseline = np.mean([tree.tree_.value[0, 0, 0] for tree in model.estimators_])

    assert np.isclose(
        attributions[0].sum(),
        model.predict(frame.iloc[[5]])[0] - baseline,
    )
    assert attributions[0][ml_scoring.MODEL_FEATURES.index("lines_added")] != 0
