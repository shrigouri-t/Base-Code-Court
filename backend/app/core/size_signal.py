"""Per-author aggregation of meaningful-line signals."""

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from math import log1p
from typing import Any

from app.core.author_key import is_probably_bot
from app.core.diff_analysis import CommitDiffStats


@dataclass(frozen=True)
class AuthorSize:
    """Aggregated contribution-size signal for one author."""

    author_key: str
    display_name: str
    display_email: str
    commits: int
    trivial_commits: int
    trivial_ratio: float
    raw_added: int
    meaningful_added: int
    meaningful_credited: int
    docs_lines_added: int
    config_lines_added: int
    bulk_commits: int
    size_score: float
    work_metrics: dict[str, Any] = field(default_factory=dict)


def _most_frequent(values: list[str]) -> str:
    """Choose the most frequent value, breaking ties alphabetically."""
    counts = Counter(values)
    return sorted(counts, key=lambda value: (-counts[value], value))[0]


def compute_size_signal(
    stats: list[CommitDiffStats],
) -> tuple[list[AuthorSize], list[AuthorSize]]:
    """Aggregate non-merge commits into humans and bots deterministically."""
    grouped: dict[str, list[CommitDiffStats]] = defaultdict(list)
    for item in stats:
        if not item.is_merge:
            grouped[item.author_key].append(item)

    def build(items: list[CommitDiffStats], score_max: int) -> AuthorSize:
        credited = sum(item.meaningful_credited for item in items)
        metrics = [item.work_metrics for item in items if item.work_metrics]
        language_distribution: Counter[str] = Counter()
        for item in metrics:
            language_distribution.update(item["language_distribution"])
        clean_lines = sum(
            item.get(
                "source_clean_nontrivial_lines",
                item["clean_nontrivial_lines"],
            )
            for item in metrics
        )
        weighted_lines = sum(
            item.get(
                "source_clean_nontrivial_lines",
                item["clean_nontrivial_lines"],
            ) * item["language_weight"]
            for item in metrics
        )
        language_weight = (
            weighted_lines / clean_lines
            if clean_lines
            else (
                sum(item["language_weight"] for item in metrics) / len(metrics)
                if metrics else 1.0
            )
        )
        work_metrics = {
            "declaration_nodes": sum(item["declaration_nodes"] for item in metrics),
            "control_nodes": sum(item["control_nodes"] for item in metrics),
            "expression_nodes": sum(item["expression_nodes"] for item in metrics),
            "ast_nodes_count": sum(item["ast_nodes_count"] for item in metrics),
            "ast_weighted_volume": round(
                sum(item["ast_weighted_volume"] for item in metrics), 2
            ),
            "nesting_depth": max(
                (item["nesting_depth"] for item in metrics), default=0
            ),
            "clean_nontrivial_lines": clean_lines,
            "source_clean_nontrivial_lines": clean_lines,
            "config_weighted_volume": round(
                sum(item.get("config_weighted_volume", 0.0) for item in metrics), 2
            ),
            "language_distribution": dict(sorted(language_distribution.items())),
            "language_weight": round(language_weight, 4),
            "ast_files_parsed": sum(item["ast_files_parsed"] for item in metrics),
            "ast_files_total": sum(item["ast_files_total"] for item in metrics),
            "refactoring_lines": sum(item["refactoring_lines"] for item in metrics),
        }
        return AuthorSize(
            author_key=items[0].author_key,
            display_name=_most_frequent([item.author_name for item in items]),
            display_email=_most_frequent([item.author_email for item in items]),
            commits=len(items),
            trivial_commits=sum(item.is_trivial for item in items),
            trivial_ratio=round(sum(item.is_trivial for item in items) / len(items), 4),
            raw_added=sum(item.raw_added for item in items),
            meaningful_added=sum(item.meaningful_added for item in items),
            meaningful_credited=credited,
            docs_lines_added=sum(item.docs_lines_added for item in items),
            config_lines_added=sum(item.config_lines_added for item in items),
            bulk_commits=sum(item.is_bulk for item in items),
            size_score=round(log1p(credited) / log1p(score_max), 4) if score_max else 0.0,
            work_metrics=work_metrics,
        )

    human_groups = [
        items for items in grouped.values()
        if not is_probably_bot(items[0].author_name, items[0].author_email)
    ]
    bot_groups = [
        items for items in grouped.values()
        if is_probably_bot(items[0].author_name, items[0].author_email)
    ]
    max_credited = max(
        (sum(item.meaningful_credited for item in items) for items in human_groups),
        default=0,
    )
    humans = [build(items, max_credited) for items in human_groups]
    bots = [build(items, max_credited) for items in bot_groups]
    humans.sort(key=lambda item: (-item.meaningful_credited, item.display_name))
    bots.sort(key=lambda item: (-item.meaningful_credited, item.display_name))
    return humans, bots
