"""Per-author quality aggregation and bounded modifier."""

from collections import Counter, defaultdict
from dataclasses import dataclass

from app.config import settings
from app.core.author_key import is_probably_bot
from app.core.diff_analysis import CommitDiffStats
from app.core.quality_analysis import CommitQualityStats, FunctionTouch


@dataclass(frozen=True)
class AuthorQuality:
    """Aggregated quality metrics for one author."""

    author_key: str
    display_name: str
    display_email: str
    functions_analyzed: int
    total_weight: int
    avg_complexity: float
    max_complexity: int
    long_functions: int
    quality_score: float
    quality_modifier: float
    low_confidence: bool


def _most_frequent(values: list[str]) -> str:
    """Choose the most frequent value with alphabetical tie-breaking."""
    counts = Counter(values)
    return sorted(counts, key=lambda value: (-counts[value], value))[0]


def _build(
    items: list[CommitQualityStats],
    diff_items: list[CommitDiffStats],
) -> AuthorQuality:
    """Build one deterministic author quality record."""
    functions = [function for item in items for function in item.functions]
    total_weight = sum(function.weight for function in functions)
    quality = (
        sum(function.quality * function.weight for function in functions) / total_weight
        if total_weight
        else 0.0
    )
    low_confidence = len(functions) < settings.MIN_FUNCTIONS_FOR_QUALITY
    legacy_modifier = (
        1.0
        if low_confidence
        else settings.QUALITY_MOD_MIN
        + (settings.QUALITY_MOD_MAX - settings.QUALITY_MOD_MIN) * quality
    )
    work_metrics = [item.work_metrics for item in diff_items if item.work_metrics]
    ast_nodes = sum(item["ast_nodes_count"] for item in work_metrics)
    control_nodes = sum(item["control_nodes"] for item in work_metrics)
    nesting_depth = max(
        (item["nesting_depth"] for item in work_metrics), default=0
    )
    has_ast_data = ast_nodes > 0 and any(
        item["ast_files_parsed"] > 0 for item in work_metrics
    )
    if has_ast_data:
        control_density = control_nodes / ast_nodes
        depth_density = min(nesting_depth / 5, 1.0)
        complexity_density = min(
            1.0, 0.7 * control_density + 0.3 * depth_density
        )
        ast_modifier = 1.3 - 0.7 * complexity_density
        modifier = min(
            1.3, max(0.6, (legacy_modifier + ast_modifier) / 2)
        )
    else:
        modifier = legacy_modifier
    return AuthorQuality(
        author_key=items[0].author_key,
        display_name=_most_frequent([item.author_name for item in items]),
        display_email=_most_frequent([item.author_email for item in items]),
        functions_analyzed=len(functions),
        total_weight=total_weight,
        avg_complexity=round(
            sum(function.cyclomatic_complexity * function.weight for function in functions)
            / total_weight,
            2,
        ) if total_weight else 0.0,
        max_complexity=max((function.cyclomatic_complexity for function in functions), default=0),
        long_functions=sum(function.nloc > 100 for function in functions),
        quality_score=round(quality, 4),
        quality_modifier=round(modifier, 4),
        low_confidence=low_confidence,
    )


def compute_quality_signal(
    stats: list[CommitQualityStats],
    diff_stats: list[CommitDiffStats] | None = None,
) -> tuple[list[AuthorQuality], list[AuthorQuality]]:
    """Aggregate quality stats into humans and bots."""
    grouped: dict[str, list[CommitQualityStats]] = defaultdict(list)
    diffs_by_author: dict[str, list[CommitDiffStats]] = defaultdict(list)
    for item in stats:
        if not item.author_key:
            continue
        grouped[item.author_key].append(item)
    for item in diff_stats or []:
        if item.author_key:
            diffs_by_author[item.author_key].append(item)
    humans: list[AuthorQuality] = []
    bots: list[AuthorQuality] = []
    for items in grouped.values():
        result = _build(items, diffs_by_author.get(items[0].author_key, []))
        (bots if is_probably_bot(items[0].author_name, items[0].author_email) else humans).append(result)
    humans.sort(key=lambda item: (-item.quality_score, item.display_name))
    bots.sort(key=lambda item: (-item.quality_score, item.display_name))
    return humans, bots


def adjusted_size(credited_lines: float, modifier: float) -> float:
    """Apply a bounded quality modifier to credited lines."""
    return round(credited_lines * modifier, 2)
