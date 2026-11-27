"""Tests for contribution scoring."""

from app.core.activity_signals import ActivityStats
from app.core.quality_signal import AuthorQuality
from app.core.scoring import compute_scores
from app.core.size_signal import AuthorSize
from app.core.survival import AuthorSurvival, SurvivalResult


def _size(key: str, name: str, credited: int) -> AuthorSize:
    return AuthorSize(key, name, f"{key}@example.com", 3, 0, 0.0, credited, credited, credited, 0, 0, 0, 0.0)


def _quality(key: str, name: str, modifier: float = 1.0) -> AuthorQuality:
    return AuthorQuality(key, name, f"{key}@example.com", 5, 5, 1.0, 1, 0, 0.5, modifier, False)


def _survival() -> SurvivalResult:
    return SurvivalResult(
        [
            AuthorSurvival("alice", "Alice", "alice@example.com", 10, 8, 0.8, 0.75, 0.6, False),
            AuthorSurvival("bob", "Bob", "bob@example.com", 5, 2, 0.4, 0.45, 0.4, False),
        ],
        [], 1.0, False, 1, {}, 0.6, {}, {
            "meaningful_lines_at_head": 10, "attributed_to_humans": 10,
            "attributed_to_bots": 0, "outside_window": 0, "unattributed": 0,
        },
    )


def test_scores_are_ranked_and_breakdowns_are_complete(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.core.scoring.predict_feature_impacts",
        lambda rows: [None] * len(rows),
    )
    report = compute_scores(
        [_size("alice", "Alice", 100), _size("bob", "Bob", 20)],
        [_quality("alice", "Alice", 1.2), _quality("bob", "Bob", 0.8)],
        _survival(),
    )

    assert [item.display_name for item in report.authors] == ["Alice", "Bob"]
    assert set(report.authors[0].signals) == {"work", "survival", "ownership", "review", "issues", "consistency"}
    assert sum(report.effective_weights.values()) == 1.0
    assert sum(
        author.signals[name].points
        for author in report.authors
        for name in report.available_signals
    ) >= 0


def test_unavailable_survival_is_renormalized_and_penalty_is_clamped(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.core.scoring.predict_feature_impacts",
        lambda rows: [None] * len(rows),
    )
    report = compute_scores(
        [_size("alice", "Alice", 10)],
        [],
        None,
        penalties={"alice": (0.1, "anomaly")},
    )
    author = report.authors[0]

    assert report.available_signals == ["work"]
    assert author.penalty_multiplier == 0.5
    assert author.signals["survival"].note == "survival not computed"
    assert "only one human author" in report.repo_notes


def test_model_prediction_is_final_score_and_receives_training_features(monkeypatch) -> None:
    captured: list[dict[str, float]] = []

    def predict(features: list[dict[str, float]]) -> list[float]:
        captured.extend(features)
        return [42.42]

    monkeypatch.setattr("app.core.scoring.predict_final_scores", predict)
    monkeypatch.setattr(
        "app.core.scoring.predict_feature_impacts",
        lambda rows: [[{"feature": "work_score", "label": "Work Signal", "impact": 2.0}]],
    )
    report = compute_scores(
        [_size("alice", "Alice", 100)],
        [_quality("alice", "Alice", 1.2)],
        _survival(),
        penalties={"alice": (0.8, "trivial_inflation")},
        extra_signals={
            "review": {"alice": 0.5},
            "issues": {"alice": 0.25},
            "consistency": {"alice": 0.75},
        },
        activity_stats={"alice": ActivityStats(3, 4, 1, 2, 5, 6, 10.0, 8.0)},
        github_data_available=True,
    )

    author = report.authors[0]
    assert author.score == 42.42
    assert author.feature_impacts == [
        {"feature": "work_score", "label": "Work Signal", "impact": 2.0}
    ]
    assert author.score != round(author.base_score * author.penalty_multiplier, 2)
    assert captured == [{
        "commits_count": 3.0,
        "lines_added": 100.0,
        "quality_modifier": 1.2,
        "adjusted_work": 120.0,
        "surviving_lines": 8.0,
        "survival_rate": 0.8,
        "prs_reviewed": 3.0,
        "issues_handled": 11.0,
        "github_data_available": 1.0,
        "work_score": 100.0,
        "survival_score": 75.0,
        "ownership_score": 100.0,
        "review_score": 50.0,
        "issues_score": 25.0,
        "consistency_score": 75.0,
        "base_score": author.base_score,
        "anomaly_flag": 1.0,
        "penalty_multiplier": 0.8,
    }]


def test_work_metadata_refines_existing_model_features_only(monkeypatch) -> None:
    from app.core.ml_scoring import MODEL_FEATURES

    captured: list[dict[str, float]] = []
    monkeypatch.setattr(
        "app.core.scoring.predict_final_scores",
        lambda rows: captured.extend(rows) or [40.0],
    )
    monkeypatch.setattr(
        "app.core.scoring.predict_feature_impacts",
        lambda rows: [None] * len(rows),
    )
    size = AuthorSize(
        "alice", "Alice", "alice@example.com", 3, 0, 0.0,
        100, 100, 100, 0, 0, 0, 0.0,
        work_metrics={
            "ast_nodes_count": 12,
            "ast_weighted_volume": 18.0,
            "declaration_nodes": 2,
            "control_nodes": 4,
            "expression_nodes": 6,
            "nesting_depth": 2,
            "clean_nontrivial_lines": 10,
            "language_distribution": {"Python": 1},
            "language_weight": 1.25,
            "ast_files_parsed": 1,
            "ast_files_total": 1,
            "refactoring_lines": 10,
        },
    )

    report = compute_scores([size], [_quality("alice", "Alice", 1.2)], None)

    assert tuple(captured[0]) == MODEL_FEATURES
    assert all(type(value) is float for value in captured[0].values())
    assert captured[0]["adjusted_work"] == 156.0
    assert report.authors[0].work_metadata["refactoring_bonus"] == 4.8
    assert report.authors[0].work_metadata["ast_nodes_count"] == 12


def test_non_penalized_anomaly_sets_model_feature(monkeypatch) -> None:
    captured: list[dict[str, float]] = []

    def predict(features: list[dict[str, float]]) -> list[float]:
        captured.extend(features)
        return [37.0]

    monkeypatch.setattr("app.core.scoring.predict_final_scores", predict)
    monkeypatch.setattr(
        "app.core.scoring.predict_feature_impacts",
        lambda rows: [None] * len(rows),
    )
    compute_scores(
        [_size("alice", "Alice", 100)],
        [],
        None,
        anomaly_flags={"alice"},
    )

    assert captured[0]["anomaly_flag"] == 1.0
    assert captured[0]["penalty_multiplier"] == 1.0


def test_model_inference_failure_uses_base_score_and_marks_impacts_unavailable(monkeypatch) -> None:
    def fail_prediction(_features):
        raise RuntimeError("model unavailable")

    monkeypatch.setattr("app.core.scoring.predict_final_scores", fail_prediction)
    report = compute_scores(
        [_size("alice", "Alice", 100)],
        [_quality("alice", "Alice", 1.2)],
        _survival(),
    )

    author = report.authors[0]
    assert author.score == author.base_score
    assert author.feature_impacts is None
    assert "ML inference unavailable; rules-based base score used." in author.notes


def test_attribution_failure_does_not_discard_model_score(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.core.scoring.predict_final_scores",
        lambda _features: [42.42],
    )

    def fail_attribution(_features):
        raise RuntimeError("explainer unavailable")

    monkeypatch.setattr(
        "app.core.scoring.predict_feature_impacts",
        fail_attribution,
    )
    report = compute_scores(
        [_size("alice", "Alice", 100)],
        [_quality("alice", "Alice", 1.2)],
        _survival(),
    )

    author = report.authors[0]
    assert author.score == 42.42
    assert author.feature_impacts is None
    assert "Feature attribution unavailable." in author.notes
