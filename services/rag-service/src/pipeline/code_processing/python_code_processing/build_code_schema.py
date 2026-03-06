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
    "id":   "cls:ClassName",
    "name": "ClassName",
    "code": "<class header + __init__ only>",  # or full class if no __init__
  }

MethodRecord:
  {
    "id":                  "mth:ClassName.method_name",
    "name":                "method_name",
    "qualified_name":      "ClassName.method_name",
    "code":                "<source of the method>",
    "class":               "cls:ClassName",          # ref -> ClassRecord.id
    "initialized_classes": ["cls:X", ...],
    "used_functions":      ["fn:foo", ...],
    "used_methods":        ["mth:Bar.baz", ...],
  }

FunctionRecord:
  {
    "id":                  "fn:function_name",
    "name":                "function_name",
    "code":                "<source of the function>",
    "initialized_classes": ["cls:X", ...],
    "used_functions":      ["fn:foo", ...],
    "used_methods":        ["mth:Bar.baz", ...],
  }
"""

import ast
import json
import textwrap
from collections.abc import Sequence
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


def _node_source(node: ast.AST) -> str:
    """Return the dedented source code for an AST node."""
    return textwrap.dedent(ast.unparse(node))


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
    """Find and return the __init__ function node in a class body, or None."""
    return next(
        (n for n in body if isinstance(n, ast.FunctionDef) and n.name == "__init__"),
        None,
    )


def _collect_known_ids(analyzer: CodeAnalyzer) -> tuple[set[str], set[str], set[str]]:
    """Collect sets of known class, method, and function ids from the analyzer."""
    return (
        {class_id(n) for n in analyzer.classes},
        {method_id(n) for n in analyzer.methods},
        {function_id(n) for n in analyzer.functions},
    )


def _refs_from_edges(
    caller: str,
    graph: dict[str, dict[str, str]],
    known_class_ids: set[str],
    known_function_ids: set[str],
    known_method_ids: set[str],
) -> tuple[list[str], list[str], list[str]]:
    """Return (initialized_classes, used_functions, used_methods) for a caller node."""
    kind_to_id = {
        KIND_CLASS_INIT: (class_id, known_class_ids),
        KIND_FUNCTION: (function_id, known_function_ids),
        KIND_METHOD: (method_id, known_method_ids),
    }
    inits: list[str] = []
    funcs: list[str] = []
    meths: list[str] = []
    buckets = {KIND_CLASS_INIT: inits, KIND_FUNCTION: funcs, KIND_METHOD: meths}

    for target, kind in graph.get(caller, {}).items():
        if kind not in kind_to_id:
            continue
        id_fn, known = kind_to_id[kind]
        ref = id_fn(target)
        if ref in known:
            buckets[kind].append(ref)

    return sorted(inits), sorted(funcs), sorted(meths)


def _fragment_algorithm_number(
    analyzer: CodeAnalyzer, key: str, class_init_key: str | None = None
) -> object:
    """Return the parsed algorithm identifier for a fragment"""
    full_number = str(analyzer.fragment_idx.get(key))
    return extract_entity_id_from_number(full_number)


def _build_classes(analyzer: CodeAnalyzer) -> list[dict[str, Any]]:
    """Build class records (id, algorithm_number, name, code) from the analyzer."""
    return [
        {
            "id": class_id(name),
            "algorithm_number": _fragment_algorithm_number(analyzer, name),
            "name": name,
            "code": _class_init_source(node),
        }
        for name, node in analyzer.classes.items()
    ]


def _build_methods(
    analyzer: CodeAnalyzer,
    graph: dict[str, dict[str, str]],
    known_class_ids: set[str],
    known_function_ids: set[str],
    known_method_ids: set[str],
) -> list[dict[str, Any]]:
    """Build method records with cross-references from analyzer and graph."""
    methods = []
    for qualified, node in analyzer.methods.items():
        cls_name, method_name = qualified.split(".", 1)
        if method_name == "__init__":
            continue  # already captured inside the class code

        inits, funcs, meths = _refs_from_edges(
            qualified, graph, known_class_ids, known_function_ids, known_method_ids
        )
        cls_ref = (
            class_id(cls_name) if class_id(cls_name) in known_class_ids else f"external:{cls_name}"
        )

        methods.append(
            {
                "id": method_id(qualified),
                "algorithm_number": _fragment_algorithm_number(analyzer, qualified),
                "name": method_name,
                "qualified_name": qualified,
                "code": ast.unparse(node),
                "class": cls_ref,
                "initialized_classes": inits,
                "used_functions": funcs,
                "used_methods": meths,
            }
        )
    return methods


def _build_functions(
    analyzer: CodeAnalyzer,
    graph: dict[str, dict[str, str]],
    known_class_ids: set[str],
    known_function_ids: set[str],
    known_method_ids: set[str],
) -> list[dict[str, Any]]:
    """Build function records with cross-references from analyzer and graph."""
    result = []
    for name, node in analyzer.functions.items():
        inits, funcs, meths = _refs_from_edges(
            name, graph, known_class_ids, known_function_ids, known_method_ids
        )
        result.append(
            {
                "id": function_id(name),
                "algorithm_number": _fragment_algorithm_number(analyzer, name),
                "name": name,
                "code": ast.unparse(node),
                "initialized_classes": inits,
                "used_functions": funcs,
                "used_methods": meths,
            }
        )
    return result


def build_code_schema(fragments: Sequence[object]) -> dict[str, list[dict[str, Any]]]:
    """
    Analyze a list of code fragments or algorithm objects and return a full
    schema of definitions with cross-references.

    Args:
        fragments: List of Python code strings or algorithm objects
                   (each may contain "code" and optional "algorithm_number").

    Returns:
        Dict with keys "classes", "methods", and "functions".
    """
    analyzer, graph = analyze_fragments(fragments)
    known_class_ids, known_method_ids, known_function_ids = _collect_known_ids(analyzer)

    ref_args = (graph, known_class_ids, known_function_ids, known_method_ids)

    return {
        "classes": _build_classes(analyzer),
        "methods": _build_methods(analyzer, *ref_args),
        "functions": _build_functions(analyzer, *ref_args),
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
