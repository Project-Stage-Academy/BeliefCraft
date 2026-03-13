"""
build_code_schema.py
--------------------
Builds a complete code schema based on CodeAnalyzer.

Returns a dict with three lists:
  {
    "classes":   [ClassRecord, ...],
    "methods":   [MethodRecord, ...],
    "functions": [FunctionRecord, ...],
  }

ClassRecord:
  {
    "id":               "cls:ClassName",
    "name":             "ClassName",
    "algorithm_number": "1.1",                # entity_id of the defining algorithm
    "code":             "<class header + __init__ only>",  # or full class if no __init__
  }

MethodRecord:
  {
    "id":                   "mth:ClassName.method_name",
    "name":                 "method_name",
    "qualified_name":       "ClassName.method_name",
    "algorithm_number":     "1.1",            # entity_id of the defining algorithm
    "code":                 "<source of the method>",
    "class":                "cls:ClassName",  # ref -> ClassRecord.id
    "initialized_classes":  ["cls:X", ...],
    "referenced_functions": ["fn:foo", ...],
    "referenced_methods":   ["mth:Bar.baz", ...],
  }

FunctionRecord:
  {
    "id":                   "fn:function_name",
    "name":                 "function_name",
    "algorithm_number":     "1.1",            # entity_id of the defining algorithm
    "code":                 "<source of the function>",
    "initialized_classes":  ["cls:X", ...],
    "referenced_functions": ["fn:foo", ...],
    "referenced_methods":   ["mth:Bar.baz", ...],
  }
"""

import ast
import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from common.logging import get_logger
from pipeline.code_processing.julia_code_translation.update_chunks_with_translated_code import (
    extract_entity_id_from_number,
)
from pipeline.code_processing.python_code_processing.code_analyzer import (
    KIND_CLASS_INIT,
    KIND_FUNCTION,
    KIND_METHOD,
    CodeAnalyzer,
    analyze_fragments,
)

logger = get_logger(__name__)


def class_id(name: str) -> str:
    """Return the canonical class id for a given class name."""
    return f"cls:{name}"


def method_id(qualified: str) -> str:
    """Return the canonical method id for a given qualified name."""
    return f"mth:{qualified}"


def function_id(name: str) -> str:
    """Return the canonical function id for a given function name."""
    return f"fn:{name}"


# ------------------------------------------------------------------ #
# AST helpers
# ------------------------------------------------------------------ #


def _class_init_source(class_node: ast.ClassDef) -> str:
    """Return class header + __init__ method (and leading docstring if present)."""
    bases = [ast.unparse(b) for b in class_node.bases]
    header = (
        f"class {class_node.name}({', '.join(bases)}):" if bases else f"class {class_node.name}:"
    )

    body = class_node.body
    docstring_node = _leading_docstring(body)
    init_node = _find_init(body)

    lines = [header]
    if docstring_node:
        lines.append(f"    {ast.unparse(docstring_node)}")
    if init_node:
        lines.extend(f"    {line}" for line in ast.unparse(init_node).splitlines())
    elif not docstring_node:
        lines.append("    ...")

    return "\n".join(lines)


def _leading_docstring(body: list[ast.stmt]) -> ast.Expr | None:
    """Return the leading docstring node from a body list, or None if absent."""
    if body:
        first = body[0]
        if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
            return first
    return None


def _find_init(body: list[ast.stmt]) -> ast.FunctionDef | None:
    """Find and return the ``__init__`` node in a class body, or None."""
    return next(
        (n for n in body if isinstance(n, ast.FunctionDef) and n.name == "__init__"),
        None,
    )


# ------------------------------------------------------------------ #
# Known-id index
# ------------------------------------------------------------------ #


@dataclass(frozen=True)
class _KnownIds:
    """Sets of canonical ref strings for all known definitions."""

    classes: frozenset[str]
    functions: frozenset[str]
    methods: frozenset[str]

    @classmethod
    def from_analyzer(cls, analyzer: CodeAnalyzer) -> "_KnownIds":
        return cls(
            classes=frozenset(class_id(n) for n in analyzer.classes),
            functions=frozenset(function_id(n) for n in analyzer.functions),
            methods=frozenset(method_id(n) for n in analyzer.methods),
        )


# ------------------------------------------------------------------ #
# Cross-reference resolution
# ------------------------------------------------------------------ #


def _refs_from_edges(
    caller: str,
    graph: dict[str, dict[str, str]],
    known: _KnownIds,
) -> tuple[list[str], list[str], list[str]]:
    """Return ``(initialized_classes, referenced_functions, referenced_methods)`` for *caller*."""
    inits: list[str] = []
    funcs: list[str] = []
    meths: list[str] = []

    for target, kind in graph.get(caller, {}).items():
        if kind == KIND_CLASS_INIT:
            ref = class_id(target)
            if ref in known.classes:
                inits.append(ref)
        elif kind == KIND_FUNCTION:
            ref = function_id(target)
            if ref in known.functions:
                funcs.append(ref)
        elif kind == KIND_METHOD:
            ref = method_id(target)
            if ref in known.methods:
                meths.append(ref)

    return sorted(inits), sorted(funcs), sorted(meths)


# ------------------------------------------------------------------ #
# Record builders
# ------------------------------------------------------------------ #


def _fragment_algorithm_number(analyzer: CodeAnalyzer, key: str) -> str:
    """Return the parsed entity_id for the algorithm fragment that defines *key*.

    E.g. if the fragment index stored ``"Algorithm 1.1."`` this returns ``"1.1"``.
    Returns an empty string when the key is not found or the number is unparseable.
    """
    raw = str(analyzer.fragment_idx.get(key, ""))
    return extract_entity_id_from_number(raw)


def _build_classes(analyzer: CodeAnalyzer) -> list[dict[str, Any]]:
    """Build class records (id, algorithm_number, name, code) from the analyzer."""
    return [
        {
            "id": class_id(name),
            "name": name,
            "algorithm_number": _fragment_algorithm_number(analyzer, name),
            "code": _class_init_source(node),
        }
        for name, node in analyzer.classes.items()
    ]


def _build_methods(
    analyzer: CodeAnalyzer,
    graph: dict[str, dict[str, str]],
    known: _KnownIds,
) -> list[dict[str, Any]]:
    """Build method records with cross-references from analyzer and graph."""
    methods = []
    for qualified, node in analyzer.methods.items():
        cls_name, method_name = qualified.split(".", 1)
        if method_name == "__init__":
            continue  # already captured inside the class code

        inits, funcs, meths = _refs_from_edges(qualified, graph, known)
        cls_ref = (
            class_id(cls_name) if class_id(cls_name) in known.classes else f"external:{cls_name}"
        )

        methods.append(
            {
                "id": method_id(qualified),
                "name": method_name,
                "qualified_name": qualified,
                "algorithm_number": _fragment_algorithm_number(analyzer, qualified),
                "code": ast.unparse(node),
                "class": cls_ref,
                "initialized_classes": inits,
                "referenced_functions": funcs,
                "referenced_methods": meths,
            }
        )
    return methods


def _build_functions(
    analyzer: CodeAnalyzer,
    graph: dict[str, dict[str, str]],
    known: _KnownIds,
) -> list[dict[str, Any]]:
    """Build function records with cross-references from analyzer and graph."""
    result = []
    for name, node in analyzer.functions.items():
        inits, funcs, meths = _refs_from_edges(name, graph, known)
        result.append(
            {
                "id": function_id(name),
                "name": name,
                "algorithm_number": _fragment_algorithm_number(analyzer, name),
                "code": ast.unparse(node),
                "initialized_classes": inits,
                "referenced_functions": funcs,
                "referenced_methods": meths,
            }
        )
    return result


# ------------------------------------------------------------------ #
# Public entry point
# ------------------------------------------------------------------ #


def build_code_schema(fragments: Sequence[object]) -> dict[str, list[dict[str, Any]]]:
    """Analyze code fragments and return a schema of definitions with cross-references.

    Args:
        fragments: Python source strings or dicts with ``"code"`` and optional
                   ``"algorithm_number"`` keys.

    Returns:
        Dict with keys ``"classes"``, ``"methods"``, and ``"functions"``.
    """
    analyzer, graph = analyze_fragments(fragments)
    known = _KnownIds.from_analyzer(analyzer)

    return {
        "classes": _build_classes(analyzer),
        "methods": _build_methods(analyzer, graph, known),
        "functions": _build_functions(analyzer, graph, known),
    }


if __name__ == "__main__":
    import sys

    input_path = sys.argv[1] if len(sys.argv) > 1 else "./translated_algorithms.json"
    output_path = sys.argv[2] if len(sys.argv) > 2 else "./schema.json"

    with Path(input_path).open() as f:
        data = json.load(f)

    schema = build_code_schema(data)

    with Path(output_path).open("w") as f:
        json.dump(schema, f, indent=2, ensure_ascii=False)

    logger.info("Classes:   %d", len(schema["classes"]))
    logger.info("Methods:   %d", len(schema["methods"]))
    logger.info("Functions: %d", len(schema["functions"]))
    logger.info("Saved to:  %s", output_path)
