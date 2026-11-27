"""Transparent contribution-score computation."""

from dataclasses import dataclass, field
import logging
from typing import Any

from app.core.activity_signals import ActivityStats
from app.core.ml_scoring import predict_feature_impacts, predict_final_scores
from app.core.quality_signal import AuthorQuality, adjusted_size
from app.core.scoring_config import (
    SIGNALS,
    ScoringConfig,
    make_config,
    scale_value,
)
from app.core.size_signal import AuthorSize
from app.core.survival import AuthorSurvival, SurvivalResult


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SignalBreakdown:
    """One author's contribution from one configured signal."""

    name: str
    raw_value: float | None
    score: float
    configured_weight: float
    effective_weight: float
    points: float
    available: bool
    note: str | None


@dataclass(frozen=True)
class AuthorScore:
    """Final score and its complete per-author breakdown."""

    author_key: str
    display_name: str
    display_email: str
    rank: int
    score: float
    base_score: float
    penalty_multiplier: float
    penalty_reasons: tuple[str, ...]
    share_of_team: float
    signals: dict[str, SignalBreakdown]
    commits: int
    credited_lines: int
    quality_modifier: float
    adjusted_size: float
    surviving_lines: int
    notes: tuple[str, ...]
    feature_impacts: list[dict] | None = None
    work_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ScoreReport:
    """Repository score report."""

    authors: list[AuthorScore]
    config: ScoringConfig
    effective_weights: dict[str, float]
    available_signals: list[str]
    dropped_signals: dict[str, str]
    repo_notes: list[str]


def _effective_weights(config: ScoringConfig, available: list[str]) -> dict[str, float]:
    total = sum(config.weights[name] for name in available)
    if total <= 0:
        raise ValueError("available scoring signals have no positive configured weight")
    result = {name: round(config.weights[name] / total, 4) for name in SIGNALS}
    result = {name: result[name] for name in available}
    drift = round(1.0 - sum(result.values()), 4)
    if drift:
        largest = max(result, key=lambda name: (result[name], -SIGNALS.index(name)))
        result[largest] = round(result[largest] + drift, 4)
    return {name: result.get(name, 0.0) for name in SIGNALS}


def _clamp_extra(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"extra signal {name} values must be numeric")
    return max(0.0, min(1.0, float(value)))


def compute_scores(
    sizes: list[AuthorSize],
    qualities: list[AuthorQuality],
    survival: SurvivalResult | None,
    config: ScoringConfig | None = None,
    penalties: dict[str, tuple[float, str]] | None = None,
    extra_signals: dict[str, dict[str, float]] | None = None,
    dropped_reasons: dict[str, str] | None = None,
    activity_stats: dict[str, ActivityStats] | None = None,
    github_data_available: bool = False,
    anomaly_flags: set[str] | None = None,
) -> ScoreReport:
    """Compute deterministic human-author contribution scores."""
    config = config or make_config()
    extra_signals = extra_signals or {}
    dropped_reasons = dropped_reasons or {}
    activity_stats = activity_stats or {}
    anomaly_flags = anomaly_flags or set()
    unknown_extra = set(extra_signals) - {"review", "issues", "consistency"}
    if unknown_extra:
        raise ValueError(f"unknown extra signal names: {', '.join(sorted(unknown_extra))}")
    quality_by_key = {item.author_key: item for item in qualities}
    survival_by_key = {
        item.author_key: item for item in survival.authors
    } if survival else {}
    refactoring_bonus_by_key: dict[str, float] = {}
    adjusted_by_key: dict[str, float] = {}
    for item in sizes:
        modifier = (
            quality_by_key[item.author_key].quality_modifier
            if item.author_key in quality_by_key else 1.0
        )
        refactoring_credit = item.work_metrics.get("refactoring_lines", 0) * 0.40
        refactoring_bonus = refactoring_credit * modifier
        effective_credited = item.meaningful_credited + refactoring_credit
        refactoring_bonus_by_key[item.author_key] = round(refactoring_bonus, 2)
        adjusted_by_key[item.author_key] = round(
            adjusted_size(effective_credited, modifier)
            * item.work_metrics.get("language_weight", 1.0),
            2,
        )
    max_adjusted = max(adjusted_by_key.values(), default=0.0)
    survival_reason = None
    survival_available = (
        survival is not None
        and not survival.partial
        and any(item.survival_score is not None for item in survival.authors)
    )
    if not survival_available:
        survival_reason = (
            "blame coverage too low" if survival is not None and survival.partial
            else "survival not computed"
        )
    available = ["work"]
    if survival_available:
        available.extend(["survival", "ownership"])
    dropped: dict[str, str] = {}
    if not survival_available:
        dropped["survival"] = survival_reason or "survival not computed"
        dropped["ownership"] = survival_reason or "survival not computed"
    for name in ("review", "issues", "consistency"):
        values = extra_signals.get(name)
        if values and any(key in values for key in (item.author_key for item in sizes)):
            available.append(name)
        else:
            dropped[name] = dropped_reasons.get(name, "not collected yet")
    effective = _effective_weights(config, available)
    penalties = penalties or {}
    draft: list[dict] = []
    for size in sizes:
        quality = quality_by_key.get(size.author_key)
        author_survival = survival_by_key.get(size.author_key)
        adjusted = adjusted_by_key[size.author_key]
        notes: list[str] = []
        if quality is None or quality.low_confidence:
            notes.append("quality unavailable or low confidence (too few analysable functions)")
        if author_survival and author_survival.low_confidence:
            notes.append("survival low confidence (few lines added)")
        if survival_available and author_survival and author_survival.survival_score is None:
            notes.append("survival unavailable for this author (no meaningful lines added)")
        if size.commits < 3:
            notes.append(f"very few commits ({size.commits})")
        if size.meaningful_credited == 0:
            notes.append("no meaningful code added")
        values = {
            "work": (adjusted, scale_value(adjusted, max_adjusted, config.scaling), None),
            "survival": (
                author_survival.survival_rate if author_survival else None,
                author_survival.survival_score if author_survival and author_survival.survival_score is not None else 0.0,
                "survival unavailable for this author (no meaningful lines added)"
                if survival_available and (not author_survival or author_survival.survival_score is None)
                else None,
            ),
            "ownership": (
                float(author_survival.surviving_lines) if author_survival else 0.0,
                scale_value(
                    float(author_survival.surviving_lines) if author_survival else 0.0,
                    max((item.surviving_lines for item in survival.authors), default=0) if survival else 0,
                    config.scaling,
                ),
                None,
            ),
        }
        for name in ("review", "issues", "consistency"):
            value = _clamp_extra(extra_signals[name][size.author_key], name) if name in extra_signals and size.author_key in extra_signals[name] else 0.0
            values[name] = (value if name in extra_signals and size.author_key in extra_signals[name] else None, value, None)
        signal_values: dict[str, SignalBreakdown] = {}
        base = 0.0
        for name in SIGNALS:
            raw, score, note = values[name]
            is_available = name in available
            if not is_available:
                score = 0.0
                note = dropped[name]
            weight = effective[name] if is_available else 0.0
            points = round(weight * round(score, 4) * 100, 2)
            base += weight * score * 100
            signal_values[name] = SignalBreakdown(
                name, None if raw is None else round(float(raw), 4), round(score, 4),
                config.weights[name], weight, points, is_available, note,
            )
        multiplier = 1.0
        penalty_reasons: tuple[str, ...] = ()
        if size.author_key in penalties:
            raw_multiplier, reason = penalties[size.author_key]
            multiplier = max(config.min_penalty_multiplier, min(1.0, float(raw_multiplier)))
            penalty_reasons = (reason,)
        activity = activity_stats.get(size.author_key)
        model_features = {
            "commits_count": float(size.commits),
            "lines_added": float(size.meaningful_credited),
            "quality_modifier": float(quality.quality_modifier if quality else 1.0),
            "adjusted_work": float(adjusted),
            "surviving_lines": float(author_survival.surviving_lines if author_survival else 0),
            "survival_rate": float(author_survival.survival_rate or 0.0) if author_survival else 0.0,
            "prs_reviewed": float(activity.prs_reviewed if activity else 0),
            "issues_handled": float(activity.issues_opened + activity.issue_comments if activity else 0),
            "github_data_available": float(github_data_available),
            "work_score": round(signal_values["work"].score * 100, 2),
            "survival_score": round(signal_values["survival"].score * 100, 2),
            "ownership_score": round(signal_values["ownership"].score * 100, 2),
            "review_score": round(signal_values["review"].score * 100, 2),
            "issues_score": round(signal_values["issues"].score * 100, 2),
            "consistency_score": round(signal_values["consistency"].score * 100, 2),
            "base_score": float(round(base, 2)),
            "anomaly_flag": float(size.author_key in anomaly_flags or bool(penalty_reasons)),
            "penalty_multiplier": float(multiplier),
        }
        draft.append({
            "size": size, "signals": signal_values, "base": round(base, 2),
            "multiplier": multiplier, "penalty_reasons": penalty_reasons, "notes": tuple(notes),
            "quality_modifier": quality.quality_modifier if quality else 1.0,
            "adjusted": adjusted, "surviving": author_survival.surviving_lines if author_survival else 0,
            "model_features": model_features,
            "work_metadata": {
                **size.work_metrics,
                "refactoring_bonus": refactoring_bonus_by_key[size.author_key],
            },
        })
    feature_rows = [item["model_features"] for item in draft]
    model_fallback = False
    try:
        predictions = predict_final_scores(feature_rows)
        if len(predictions) != len(draft):
            raise ValueError("model returned an unexpected number of scores")
    except Exception:
        logger.exception("ML score inference failed; using rules-based base scores")
        predictions = [item["base"] for item in draft]
        feature_impacts = [None] * len(draft)
        model_fallback = True
    else:
        try:
            feature_impacts = predict_feature_impacts(feature_rows)
            if len(feature_impacts) != len(draft):
                raise ValueError("attribution returned an unexpected number of rows")
        except Exception:
            logger.exception("Feature attribution failed; returning scores without impacts")
            feature_impacts = [None] * len(draft)

    for item, score, impacts in zip(draft, predictions, feature_impacts):
        item["final_score"] = score
        item["feature_impacts"] = impacts
        if model_fallback:
            item["notes"] = item["notes"] + (
                "ML inference unavailable; rules-based base score used.",
            )
        elif impacts is None:
            item["notes"] = item["notes"] + ("Feature attribution unavailable.",)
    final_total = sum(item["final_score"] for item in draft)
    draft.sort(key=lambda item: (-item["final_score"], item["size"].display_name, item["size"].author_key))
    authors = []
    for rank, item in enumerate(draft, 1):
        final_score = item["final_score"]
        authors.append(AuthorScore(
            item["size"].author_key, item["size"].display_name, item["size"].display_email,
            rank, final_score, item["base"], round(item["multiplier"], 4),
            item["penalty_reasons"],
            round(final_score / final_total * 100, 2) if final_total else 0.0,
            item["signals"], item["size"].commits, item["size"].meaningful_credited,
            item["quality_modifier"], item["adjusted"], item["surviving"], item["notes"],
            item["feature_impacts"], item["work_metadata"],
        ))
    repo_notes = [f"{name}: {reason}" for name, reason in dropped.items()]
    if len(sizes) == 1:
        repo_notes.append("only one human author")
    return ScoreReport(authors, config, effective, [name for name in SIGNALS if name in available], dropped, repo_notes)
