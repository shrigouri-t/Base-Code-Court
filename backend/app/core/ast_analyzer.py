"""Tree-Sitter metrics for changed code, with line-count fallbacks."""

from pathlib import PurePath
from threading import local
from typing import Any

from app.core.line_classifier import classify_added_line


PARSER_BY_EXTENSION = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".rs": "rust",
    ".go": "go",
    ".java": "java",
    ".cpp": "cpp",
}

LANGUAGE_BY_EXTENSION = {
    ".py": "Python",
    ".js": "JavaScript",
    ".ts": "TypeScript",
    ".rs": "Rust",
    ".go": "Go",
    ".java": "Java",
    ".cpp": "C++",
    ".html": "HTML",
    ".css": "CSS",
    ".sh": "Shell",
    ".json": "JSON",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".lock": "Lockfile",
}

LANGUAGE_WEIGHTS = {
    ".rs": 1.25,
    ".cpp": 1.25,
    ".go": 1.25,
    ".py": 1.0,
    ".ts": 1.0,
    ".js": 1.0,
    ".java": 1.0,
    ".html": 0.5,
    ".css": 0.5,
    ".sh": 0.5,
    ".json": 0.2,
    ".yaml": 0.2,
    ".yml": 0.2,
    ".lock": 0.2,
}

_parser_state = local()


_DECLARATION_TYPES = {
    "class_declaration",
    "class_definition",
    "class_specifier",
    "constructor_declaration",
    "enum_declaration",
    "enum_item",
    "field_declaration",
    "function_declaration",
    "function_definition",
    "function_item",
    "impl_item",
    "interface_declaration",
    "let_declaration",
    "lexical_declaration",
    "method_declaration",
    "method_definition",
    "namespace_definition",
    "static_item",
    "struct_item",
    "struct_specifier",
    "trait_item",
    "type_alias_declaration",
    "type_declaration",
    "type_item",
    "var_declaration",
    "variable_declaration",
}

_CONTROL_TYPES = {
    "break_statement",
    "case_clause",
    "catch_clause",
    "continue_statement",
    "do_statement",
    "elif_clause",
    "else_clause",
    "for_expression",
    "for_statement",
    "if_expression",
    "if_statement",
    "loop_expression",
    "match_expression",
    "match_statement",
    "return_statement",
    "switch_expression",
    "switch_statement",
    "throw_statement",
    "try_statement",
    "while_expression",
    "while_statement",
}

_NESTING_TYPES = {
    "case_clause",
    "catch_clause",
    "do_statement",
    "elif_clause",
    "else_clause",
    "for_expression",
    "for_statement",
    "if_expression",
    "if_statement",
    "loop_expression",
    "match_expression",
    "match_statement",
    "switch_expression",
    "switch_statement",
    "try_statement",
    "while_expression",
    "while_statement",
}

_EXPRESSION_TYPES = {
    "arrow_function",
    "assignment",
    "assignment_expression",
    "binary_operator",
    "call",
    "call_expression",
    "lambda",
    "unary_operator",
    "update_expression",
}


def _get_parser(grammar: str) -> Any:
    parsers = getattr(_parser_state, "parsers", None)
    if parsers is None:
        parsers = {}
        _parser_state.parsers = parsers
    if grammar not in parsers:
        from tree_sitter_language_pack import get_parser

        parsers[grammar] = get_parser(grammar)
    return parsers[grammar]


def language_weight(file_path: str) -> float:
    """Return the configured difficulty multiplier for a file extension."""
    return LANGUAGE_WEIGHTS.get(PurePath(file_path).suffix.lower(), 1.0)


def _diff_chunks(diff_hunks: str) -> list[list[tuple[str, bool]]]:
    lines = diff_hunks.splitlines()
    if not any(line.startswith("@@") for line in lines):
        source_lines = [
            line[1:] if line.startswith("+") else line
            for line in lines
            if not line.startswith(("+++", "---"))
        ]
        return [[(line, True) for line in source_lines]] if source_lines else []

    chunks: list[list[tuple[str, bool]]] = []
    current: list[tuple[str, bool]] | None = None
    for line in lines:
        if line.startswith("@@"):
            if current:
                chunks.append(current)
            current = []
        elif current is None or line.startswith("\\"):
            continue
        elif line.startswith("+++"):
            continue
        elif line.startswith("+"):
            current.append((line[1:], True))
        elif line.startswith("-"):
            continue
        elif line.startswith(" "):
            current.append((line[1:], False))
    if current:
        chunks.append(current)
    return chunks


def _clean_nontrivial_lines(lines: list[str], extension: str) -> int:
    if extension == ".md":
        ignored_markers = ("#", "```", "~~~", "---", "***", "___")
        return sum(
            bool(line.strip())
            and not line.lstrip().startswith(ignored_markers)
            and line.strip() not in {"|---|", "| --- |"}
            for line in lines
        )

    count = 0
    in_block_comment = False
    for line in lines:
        stripped = line.strip()
        if extension in {".yaml", ".yml"} and stripped.startswith("#"):
            continue
        category, in_block_comment = classify_added_line(
            line, extension, in_block_comment
        )
        if category == "meaningful":
            count += 1
    return count


def _fallback_result(
    file_path: str,
    lines: list[str],
    language: str,
) -> dict[str, Any]:
    extension = PurePath(file_path).suffix.lower()
    clean_lines = _clean_nontrivial_lines(lines, extension)
    return {
        "declaration_nodes": 0,
        "control_nodes": 0,
        "expression_nodes": 0,
        "ast_nodes_count": 0,
        "ast_weighted_volume": round(clean_lines * language_weight(file_path), 2),
        "nesting_depth": 0,
        "clean_nontrivial_lines": clean_lines,
        "language": LANGUAGE_BY_EXTENSION.get(extension, language or extension or "Other"),
        "language_weight": language_weight(file_path),
        "is_ast_parsed": False,
    }


def _node_category(node_type: str) -> str | None:
    if node_type == "comment" or node_type.endswith("_comment"):
        return None
    if node_type in {
        "import_declaration",
        "import_from_statement",
        "import_statement",
        "package_clause",
        "package_declaration",
        "use_declaration",
    }:
        return None
    if node_type in _DECLARATION_TYPES:
        return "declaration"
    if node_type.endswith(("_declaration", "_definition", "_item")):
        return "declaration"
    if node_type in _CONTROL_TYPES:
        return "control"
    if node_type in _EXPRESSION_TYPES or node_type.endswith("_expression"):
        return "expression"
    return None


def _parse_chunks(
    file_path: str,
    chunks: list[list[tuple[str, bool]]],
    language: str,
) -> dict[str, Any] | None:
    extension = PurePath(file_path).suffix.lower()
    grammar = PARSER_BY_EXTENSION.get(extension)
    if grammar is None:
        return None

    declaration_nodes = 0
    control_nodes = 0
    expression_nodes = 0
    nesting_depth = 0
    clean_lines = 0
    for chunk in chunks:
        source_lines = [line for line, _ in chunk]
        changed_rows = {
            index for index, (_, changed) in enumerate(chunk) if changed
        }
        clean_lines += _clean_nontrivial_lines(
            [line for line, changed in chunk if changed], extension
        )
        if not changed_rows:
            continue
        source = "\n".join(source_lines).encode("utf-8")
        root = _get_parser(grammar).parse(source).root_node
        if root.has_error:
            return None

        def visit(node: Any, current_control_depth: int) -> None:
            nonlocal declaration_nodes, control_nodes, expression_nodes, nesting_depth
            start_row = node.start_point.row
            end_row = node.end_point.row
            touches_change = any(start_row <= row <= end_row for row in changed_rows)
            category = _node_category(node.type) if touches_change else None
            depth = current_control_depth
            if category == "declaration":
                declaration_nodes += 1
            elif category == "control":
                control_nodes += 1
                if node.type in _NESTING_TYPES:
                    depth += 1
                    nesting_depth = max(nesting_depth, depth)
            elif category == "expression":
                expression_nodes += 1
            for child in node.named_children:
                visit(child, depth)

        visit(root, 0)

    ast_nodes_count = declaration_nodes + control_nodes + expression_nodes
    if ast_nodes_count == 0 and clean_lines == 0:
        return {
            "declaration_nodes": 0,
            "control_nodes": 0,
            "expression_nodes": 0,
            "ast_nodes_count": 0,
            "ast_weighted_volume": 0.0,
            "nesting_depth": 0,
            "clean_nontrivial_lines": 0,
            "language": LANGUAGE_BY_EXTENSION.get(extension, language or extension or "Other"),
            "language_weight": language_weight(file_path),
            "is_ast_parsed": True,
        }

    weight = language_weight(file_path)
    volume = (
        declaration_nodes * 1.5 + control_nodes * 2.0 + expression_nodes
    ) * weight
    return {
        "declaration_nodes": declaration_nodes,
        "control_nodes": control_nodes,
        "expression_nodes": expression_nodes,
        "ast_nodes_count": ast_nodes_count,
        "ast_weighted_volume": round(volume, 2),
        "nesting_depth": nesting_depth,
        "clean_nontrivial_lines": clean_lines,
        "language": LANGUAGE_BY_EXTENSION.get(extension, language or extension or "Other"),
        "language_weight": weight,
        "is_ast_parsed": True,
    }


def count_diff_ast_nodes(
    file_path: str,
    diff_hunks: str,
    language: str,
) -> dict[str, Any]:
    """Count changed semantic nodes or fall back to clean changed-line volume."""
    chunks = _diff_chunks(diff_hunks)
    changed_lines = [
        line for chunk in chunks for line, changed in chunk if changed
    ]
    try:
        parsed = _parse_chunks(file_path, chunks, language)
    except Exception:
        parsed = None
    if parsed is not None:
        return parsed
    return _fallback_result(file_path, changed_lines, language)


def count_source_ast_nodes(
    file_path: str,
    source: str | None,
    language: str,
) -> dict[str, Any]:
    """Count semantic nodes in a complete source file for structural comparison."""
    if source is None:
        return _fallback_result(file_path, [], language)
    lines = source.splitlines()
    try:
        parsed = _parse_chunks(
            file_path,
            [[(line, True) for line in lines]],
            language,
        )
    except Exception:
        parsed = None
    if parsed is not None:
        return parsed
    return _fallback_result(file_path, lines, language)
