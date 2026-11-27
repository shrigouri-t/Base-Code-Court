import pytest

from app.core.ast_analyzer import count_diff_ast_nodes, language_weight


def test_ast_nodes_and_weighted_volume_for_supported_source() -> None:
    diff = (
        "@@ -0,0 +1,4 @@\n"
        "+def calculate(value):\n"
        "+    if value > 0:\n"
        "+        return value + 1\n"
        "+    return 0\n"
    )

    metrics = count_diff_ast_nodes("src/calculate.py", diff, "Python")

    assert metrics["is_ast_parsed"]
    assert metrics["declaration_nodes"] > 0
    assert metrics["control_nodes"] > 0
    assert metrics["nesting_depth"] == 1
    assert metrics["ast_weighted_volume"] == (
        metrics["declaration_nodes"] * 1.5
        + metrics["control_nodes"] * 2.0
        + metrics["expression_nodes"]
    )


def test_unsupported_markdown_uses_clean_line_fallback() -> None:
    for path, diff, expected in (
        (
            "README.md",
            "@@ -0,0 +1,4 @@\n+## Overview\n+\n+Useful explanation.\n+~~~\n",
            1,
        ),
        ("notes.txt", "@@ -0,0 +1,2 @@\n+Plain text line\n+\n", 1),
    ):
        metrics = count_diff_ast_nodes(path, diff, "Text")
        assert not metrics["is_ast_parsed"]
        assert metrics["clean_nontrivial_lines"] == expected


@pytest.mark.parametrize(
    ("extension", "source"),
    (
        (".js", "function f(x) { if (x) return x + 1; }"),
        (".ts", "function f(x: number): number { return x + 1; }"),
        (".rs", "fn f(x: i32) -> i32 { if x > 0 { x + 1 } else { 0 } }"),
        (".go", "func f(x int) int { return x + 1 }"),
        (".java", "class Example { int f(int x) { return x + 1; } }"),
        (".cpp", "int f(int x) { return x + 1; }"),
    ),
)
def test_supported_language_parsers(extension: str, source: str) -> None:
    diff = f"@@ -0,0 +1,1 @@\n+{source}\n"

    metrics = count_diff_ast_nodes(f"src/example{extension}", diff, extension)

    assert metrics["is_ast_parsed"]
    assert metrics["ast_nodes_count"] > 0


def test_language_difficulty_weights() -> None:
    assert language_weight("src/lib.rs") == 1.25
    assert language_weight("src/page.html") == 0.5
    assert language_weight("config.json") == 0.2
    assert language_weight("README.md") == 1.0
