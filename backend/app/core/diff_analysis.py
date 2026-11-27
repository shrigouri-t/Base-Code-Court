"""Diff analysis for triviality and meaningful-line signals."""

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

from pydriller import Repository

from app.config import settings
from app.core.author_key import author_key, is_probably_bot
from app.core.file_filters import classify_path
from app.core.line_classifier import classify_added_line
from app.core.quality_analysis import CommitQualityStats, analyze_commit_quality
from app.core.ast_analyzer import count_diff_ast_nodes, count_source_ast_nodes


@dataclass(frozen=True)
class FileDiffStats:
    """Normalized statistics for one modified file."""

    path: str
    category: str
    change_type: str
    raw_added: int
    raw_deleted: int
    blank: int
    comment: int
    import_: int
    punctuation: int
    formatting_churn: int
    meaningful_added: int
    skipped_reason: str | None
    work_metrics: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CommitDiffStats:
    """Normalized statistics for one commit."""

    hash: str
    author_key: str
    author_name: str
    author_email: str
    authored_at: datetime
    is_merge: bool
    is_bot: bool
    files_total: int
    files_source: int
    raw_added: int
    meaningful_added: int
    meaningful_credited: int
    docs_lines_added: int
    config_lines_added: int
    ignored_files: int
    is_bulk: bool
    is_trivial: bool
    skipped_files: list[str]
    work_metrics: dict[str, Any] = field(default_factory=dict)


def _change_type(file: Any) -> str:
    """Return a stable change type string across PyDriller versions."""
    value = getattr(file, "change_type", "")
    return getattr(value, "name", str(value)).upper()


def _normalized(value: str) -> str:
    """Remove whitespace for formatting-churn matching."""
    return "".join(value.split())


def _meaningful_deleted(lines: list[tuple[int, str]], extension: str) -> int:
    """Count substantive deleted lines for refactoring-candidate detection."""
    count = 0
    block = False
    for _, text in lines:
        category, block = classify_added_line(text, extension, block)
        if category == "meaningful":
            count += 1
    return count


def _file_work_metrics(
    file: Any,
    path: str,
    extension: str,
    category: str,
    deleted_lines: list[tuple[int, str]],
    formatting_churn: int,
) -> dict[str, Any]:
    """Collect AST diagnostics and a refactoring candidate for one file."""
    language = extension.lstrip(".").upper() or "Other"
    metrics = count_diff_ast_nodes(path, file.diff or "", language)
    refactoring_lines = 0
    if category == "source" and deleted_lines:
        before = count_source_ast_nodes(
            path, getattr(file, "source_code_before", None), language
        )
        after = count_source_ast_nodes(
            path, getattr(file, "source_code", None), language
        )
        if (
            before["is_ast_parsed"]
            and after["is_ast_parsed"]
            and before["declaration_nodes"] > 0
            and 0 < after["declaration_nodes"] <= before["declaration_nodes"]
        ):
            refactoring_lines = max(
                0,
                min(
                    _meaningful_deleted(deleted_lines, extension),
                    len(deleted_lines) - formatting_churn,
                ),
            )
    return {**metrics, "refactoring_lines": refactoring_lines}


def _file_stats(file: Any) -> FileDiffStats:
    """Analyze one PyDriller modified-file object."""
    path = file.new_path or file.old_path or ""
    category = classify_path(path)
    change_type = _change_type(file)
    parsed = file.diff_parsed
    if parsed is None or "\x00" in (file.diff or ""):
        return FileDiffStats(path, category, change_type, 0, 0, 0, 0, 0, 0, 0, 0, "binary")
    added = list(parsed.get("added", []))
    deleted = list(parsed.get("deleted", []))
    if change_type == "RENAME" and not added and not deleted:
        return FileDiffStats(path, category, change_type, 0, 0, 0, 0, 0, 0, 0, 0, "pure rename")
    if not added and not deleted:
        return FileDiffStats(path, category, change_type, 0, 0, 0, 0, 0, 0, 0, 0, "binary")
    if len(added) > settings.MAX_FILE_DIFF_LINES:
        return FileDiffStats(
            path, category, change_type, len(added), len(deleted), 0, 0, 0, 0, 0, 0,
            "too large (likely generated or pasted)",
        )

    deleted_lines = Counter(_normalized(text) for _, text in deleted if _normalized(text))
    counts = Counter()
    meaningful = 0
    churn = 0
    block = False
    ext = "." + path.rsplit(".", 1)[-1].lower() if "." in path.rsplit("/", 1)[-1] else ""
    for _, text in added:
        normalized = _normalized(text)
        if normalized and deleted_lines[normalized]:
            deleted_lines[normalized] -= 1
            churn += 1
            continue
        line_category, block = classify_added_line(text, ext, block)
        counts[line_category] += 1
        if line_category == "meaningful" and category == "source":
            meaningful += 1
    extension = "." + path.rsplit(".", 1)[-1].lower() if "." in path.rsplit("/", 1)[-1] else ""
    work_metrics = _file_work_metrics(
        file, path, extension, category, deleted, churn
    )
    return FileDiffStats(
        path=path,
        category=category,
        change_type=change_type,
        raw_added=len(added),
        raw_deleted=len(deleted),
        blank=counts["blank"],
        comment=counts["comment"],
        import_=counts["import"],
        punctuation=counts["punctuation"],
        formatting_churn=churn,
        meaningful_added=meaningful,
        skipped_reason=None,
        work_metrics=work_metrics,
    )


def _aggregate_work_metrics(files: list[FileDiffStats]) -> dict[str, Any]:
    """Aggregate source-file diagnostics without mixing them into model inputs."""
    metrics = [
        item.work_metrics for item in files
        if item.category in {"source", "config"} and item.work_metrics
    ]
    source_metrics = [
        item.work_metrics for item in files
        if item.category == "source" and item.work_metrics
    ]
    config_metrics = [
        item.work_metrics for item in files
        if item.category == "config" and item.work_metrics
    ]
    language_files = Counter(item["language"] for item in metrics)
    clean_lines = sum(item["clean_nontrivial_lines"] for item in metrics)
    source_clean_lines = sum(
        item["clean_nontrivial_lines"] for item in source_metrics
    )
    source_weighted_lines = sum(
        item["clean_nontrivial_lines"] * item["language_weight"]
        for item in source_metrics
    )
    language_weight = (
        source_weighted_lines / source_clean_lines
        if source_clean_lines
        else (
            sum(item["language_weight"] for item in source_metrics)
            / len(source_metrics)
            if source_metrics else 1.0
        )
    )
    return {
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
        "source_clean_nontrivial_lines": source_clean_lines,
        "config_weighted_volume": round(
            sum(item["ast_weighted_volume"] for item in config_metrics), 2
        ),
        "language_distribution": dict(sorted(language_files.items())),
        "language_weight": round(language_weight, 4),
        "ast_files_parsed": sum(bool(item["is_ast_parsed"]) for item in metrics),
        "ast_files_total": len(metrics),
        "refactoring_lines": sum(
            item["refactoring_lines"] for item in source_metrics
        ),
    }


def analyze_commit(commit: Any) -> CommitDiffStats:
    """Analyze one commit and never load diffs for merge commits."""
    author = commit.author
    key = author_key(author.name, author.email)
    bot = is_probably_bot(author.name, author.email)
    if commit.merge:
        return CommitDiffStats(
            commit.hash, key, author.name, author.email, commit.author_date, True, bot,
            0, 0, 0, 0, 0, 0, 0, 0, False, True, [],
        )

    files = list(commit.modified_files)
    stats: list[FileDiffStats] = []
    skipped: list[str] = []
    for file in files:
        try:
            result = _file_stats(file)
        except Exception as error:
            path = file.new_path or file.old_path or ""
            result = FileDiffStats(
                path, classify_path(path), _change_type(file), 0, 0, 0, 0, 0, 0, 0, 0,
                f"error: {type(error).__name__}",
            )
        stats.append(result)
        if result.skipped_reason:
            skipped.append(result.skipped_reason)

    meaningful = sum(item.meaningful_added for item in stats)
    return CommitDiffStats(
        hash=commit.hash,
        author_key=key,
        author_name=author.name,
        author_email=author.email,
        authored_at=commit.author_date,
        is_merge=False,
        is_bot=bot,
        files_total=len(files),
        files_source=sum(item.category == "source" for item in stats),
        raw_added=sum(item.raw_added for item in stats),
        meaningful_added=meaningful,
        meaningful_credited=min(meaningful, settings.COMMIT_MEANINGFUL_CAP),
        docs_lines_added=sum(item.raw_added for item in stats if item.category == "docs"),
        config_lines_added=sum(item.raw_added for item in stats if item.category == "config"),
        ignored_files=sum(item.category == "ignored" for item in stats),
        is_bulk=len(files) > settings.MAX_FILES_PER_COMMIT,
        is_trivial=meaningful < settings.TRIVIAL_COMMIT_THRESHOLD,
        skipped_files=skipped,
        work_metrics=_aggregate_work_metrics(stats),
    )


def analyze_repo(
    repo_path: Any,
    max_commits: int | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    progress: Callable[[int, int], None] | None = None,
) -> list[CommitDiffStats]:
    """Analyze the newest selected commits in repository order."""
    results, _ = _analyze_repo_selected(
        repo_path, max_commits, since, until, progress, include_quality=False
    )
    return results


def _analyze_repo_selected(
    repo_path: Any,
    max_commits: int | None,
    since: datetime | None,
    until: datetime | None,
    progress: Callable[[int, int], None] | None,
    include_quality: bool,
) -> tuple[list[CommitDiffStats], list[CommitQualityStats]]:
    """Traverse the selected newest commits once for one or both analyses."""
    limit = settings.DEFAULT_MAX_COMMITS if max_commits is None else max_commits
    if limit < 0:
        raise ValueError("max_commits must be non-negative.")
    hashes = [
        commit.hash
        for commit in Repository(
            str(repo_path), since=since, to=until, only_no_merge=False
        ).traverse_commits()
    ]
    selected = hashes[-limit:] if limit else []
    diff_results: list[CommitDiffStats] = []
    quality_results: list[CommitQualityStats] = []
    for index, commit in enumerate(
        Repository(
            str(repo_path), since=since, to=until, only_no_merge=False,
            only_commits=selected,
        ).traverse_commits(),
        start=1,
    ):
        diff_results.append(analyze_commit(commit))
        if include_quality:
            quality_results.append(analyze_commit_quality(commit))
        if progress and index % 25 == 0:
            progress(index, len(selected))
    return diff_results, quality_results


def analyze_repo_full(
    repo_path: Any,
    max_commits: int | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    progress: Callable[[int, int], None] | None = None,
) -> tuple[list[CommitDiffStats], list[CommitQualityStats]]:
    """Analyze Stage 3 and Stage 4 signals in one commit traversal."""
    return _analyze_repo_selected(
        repo_path, max_commits, since, until, progress, include_quality=True
    )
