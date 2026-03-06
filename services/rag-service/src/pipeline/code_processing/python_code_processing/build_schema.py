"""
build_schema.py
---------------
Будує повну схему коду на основі CodeAnalyzer.

Результат — словник з трьома списками:
  {
    "classes":   [ClassRecord, ...],
    "methods":   [MethodRecord, ...],
    "functions": [FunctionRecord, ...],
  }

ClassRecord:
  {
    "id":   "cls:ClassName",
    "name": "ClassName",
    "code": "<тільки __init__ + рядок class ...>",  # або весь клас якщо немає __init__
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
from pathlib import Path

from pipeline.code_processing.julia_code_translation.update_chunks_with_translated_code import (
    extract_entity_id_from_number,
)
from pipeline.code_processing.python_code_processing.code_analyzer import (
    KIND_CLASS_INIT,
    KIND_FUNCTION,
    KIND_METHOD,
    analyze_fragments,
)

# ------------------------------------------------------------------ #
# ID helpers
# ------------------------------------------------------------------ #


def class_id(name: str) -> str:
    return f"cls:{name}"


def method_id(qualified: str) -> str:
    return f"mth:{qualified}"


def function_id(name: str) -> str:
    return f"fn:{name}"


# ------------------------------------------------------------------ #
# Source extraction
# ------------------------------------------------------------------ #


def _node_source(node: ast.AST) -> str:
    """Return cleaned source for an AST node."""
    return textwrap.dedent(ast.unparse(node))


def _class_init_source(class_node: ast.ClassDef) -> str:
    """
    Extract only the class header + __init__ method.
    If __init__ is absent, return just the class header with '...'.
    Docstring of the class is preserved if present.
    """
    bases = [ast.unparse(b) for b in class_node.bases]
    header = (
        f"class {class_node.name}({', '.join(bases)}):" if bases else f"class {class_node.name}:"
    )
    lines = [header]

    body = class_node.body

    # Keep leading docstring
    docstring_node: ast.Expr | None = None
    if body:
        first = body[0]
        if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
            docstring_node = first

    init_node: ast.FunctionDef | None = next(
        (n for n in body if isinstance(n, ast.FunctionDef) and n.name == "__init__"),
        None,
    )

    if docstring_node:
        doc = ast.unparse(docstring_node)
        lines.append(f"    {doc}")

    if isinstance(init_node, ast.FunctionDef):
        init_src = ast.unparse(init_node)
        for line in init_src.splitlines():
            lines.append(f"    {line}")
    else:
        if not docstring_node:
            lines.append("    ...")

    return "\n".join(lines)


def _method_source(method_node: ast.FunctionDef) -> str:
    """Return the full source of a method (unindented)."""
    return ast.unparse(method_node)


def _function_source(func_node: ast.FunctionDef) -> str:
    """Return the full source of a top-level function."""
    return ast.unparse(func_node)


# ------------------------------------------------------------------ #
# Schema builder
# ------------------------------------------------------------------ #


def build_schema(fragments: list[object]) -> dict[str, list[dict[str, object]]]:
    """
    Аналізує список фрагментів коду або алгоритмів і повертає повну схему визначень
    з посиланнями між ними.

    Args:
        fragments: список рядків Python-коду або об'єктів-алгоритмів (кожен може містити
                   ключі "code" і опційно "algorithm_number").

    Returns:
        Словник {"classes": [...], "methods": [...], "functions": [...]}.
    """
    analyzer, graph = analyze_fragments(fragments)

    # -------------------------------------------------------------- #
    # 1. Зібрати всі відомі ID заздалегідь (для перевірки посилань)
    # -------------------------------------------------------------- #

    known_class_ids: set[str] = {class_id(n) for n in analyzer.classes}
    known_method_ids: set[str] = {method_id(n) for n in analyzer.methods}
    known_function_ids: set[str] = {function_id(n) for n in analyzer.functions}

    def _refs_from_edges(caller: str) -> tuple[list[str], list[str], list[str]]:
        """
        Розбирає ребра графу для `caller` і повертає три списки ID:
          (initialized_classes, used_functions, used_methods)
        Тільки посилання на відомі визначення включаються.
        """
        edges: dict[str, str] = graph.get(caller, {})
        inits, funcs, meths = [], [], []
        for target, kind in edges.items():
            if kind == KIND_CLASS_INIT:
                ref = class_id(target)
                if ref in known_class_ids:
                    inits.append(ref)
            elif kind == KIND_FUNCTION:
                ref = function_id(target)
                if ref in known_function_ids:
                    funcs.append(ref)
            elif kind == KIND_METHOD:
                ref = method_id(target)
                if ref in known_method_ids:
                    meths.append(ref)
        return sorted(inits), sorted(funcs), sorted(meths)

    # -------------------------------------------------------------- #
    # 2. Класи
    # -------------------------------------------------------------- #

    classes: list[dict[str, object]] = []
    for name, class_node in analyzer.classes.items():
        # Prefer the algorithm_number that contains __init__ (the "primary" definition).
        # Fall back to the fragment/algorithm origin where the class header was seen.
        alg_num = analyzer._class_init_fragment.get(name, analyzer.fragment_idx.get(name))
        classes.append(
            {
                "id": class_id(name),
                "algorithm_number": extract_entity_id_from_number(str(alg_num)),
                "name": name,
                "code": _class_init_source(class_node),
            }
        )

    # -------------------------------------------------------------- #
    # 3. Методи
    # -------------------------------------------------------------- #

    methods: list[dict[str, object]] = []
    for qualified, method_node in analyzer.methods.items():
        # qualified = "ClassName.method_name"
        cls_name, method_name = qualified.split(".", 1)

        # __init__ is already captured inside the class code — skip as separate method
        if method_name == "__init__":
            continue
        inits, funcs, meths = _refs_from_edges(qualified)

        # Посилання на клас (може бути визначений в іншому фрагменті)
        cls_ref = class_id(cls_name)
        if cls_ref not in known_class_ids:
            # Клас не знайдено серед визначень — зберігаємо ref все одно,
            # але позначаємо як зовнішній (без префіксу "cls:")
            cls_ref = f"external:{cls_name}"

        methods.append(
            {
                "id": method_id(qualified),
                "algorithm_number": extract_entity_id_from_number(
                    str(analyzer.fragment_idx.get(qualified))
                ),
                "name": method_name,
                "qualified_name": qualified,
                "code": _method_source(method_node),
                "class": cls_ref,
                "initialized_classes": inits,
                "used_functions": funcs,
                "used_methods": meths,
            }
        )

    # -------------------------------------------------------------- #
    # 4. Функції
    # -------------------------------------------------------------- #

    functions: list[dict[str, object]] = []
    for name, func_node in analyzer.functions.items():
        inits, funcs, meths = _refs_from_edges(name)
        functions.append(
            {
                "id": function_id(name),
                "algorithm_number": extract_entity_id_from_number(
                    str(analyzer.fragment_idx.get(name))
                ),
                "name": name,
                "code": _function_source(func_node),
                "initialized_classes": inits,
                "used_functions": funcs,
                "used_methods": meths,
            }
        )

    return {
        "classes": classes,
        "methods": methods,
        "functions": functions,
    }


# ------------------------------------------------------------------ #
# Entry point
# ------------------------------------------------------------------ #

if __name__ == "__main__":
    import sys

    input_path = sys.argv[1] if len(sys.argv) > 1 else "./translated_algorithms.json"
    output_path = sys.argv[2] if len(sys.argv) > 2 else "./schema.json"

    with Path(input_path).open() as f:
        data = json.load(f)

    # data is expected to be a list of algorithm objects; pass them directly
    schema = build_schema(data)

    with Path(output_path).open("w") as f:
        json.dump(schema, f, indent=2, ensure_ascii=False)

    print(f"Classes:   {len(schema['classes'])}")
    print(f"Methods:   {len(schema['methods'])}")
    print(f"Functions: {len(schema['functions'])}")
    print(f"Saved to:  {output_path}")
