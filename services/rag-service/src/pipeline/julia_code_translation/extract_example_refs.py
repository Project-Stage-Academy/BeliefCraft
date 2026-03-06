"""
extract_example_refs.py
-----------------------
Витягує посилання на класи, методи та функції з "прикладів" —
фрагментів що містять звичайний текст з вбудованими ```python блоками.

На відміну від code_analyzer, тут ми НЕ реєструємо нові визначення,
а лише збираємо виклики і резолвимо їх проти вже відомої схеми.

Результат:
  {
    "initialized_classes": ["cls:X", ...],
    "used_functions":      ["fn:foo", ...],
    "used_methods":        ["mth:Bar.baz", ...],
  }
"""

import ast
import re
from collections import defaultdict

from pipeline.julia_code_translation.code_analyzer import (
    EXTERNAL_MODULES,
)

# ------------------------------------------------------------------ #
# Extract python code blocks from markdown/prose text
# ------------------------------------------------------------------ #

_CODE_BLOCK_RE = re.compile(r"```python\s*\n(.*?)```", re.DOTALL)
_MATH_BLOCK_RE = re.compile(r"\$\$.*?\$\$", re.DOTALL)  # strip LaTeX blocks
_MATH_INLINE_RE = re.compile(r"\$[^$]+\$")  # strip inline LaTeX


def _is_code_line(line: str) -> bool:
    """
    Евристика: чи виглядає рядок як Python-код, а не як звичайний текст.
    Перевіряємо чи парситься як валідний Python вираз/Statement.
    """
    stripped = line.strip()
    if not stripped:
        return False
    # Явні ознаки тексту: починається з великої літери і не містить '=' чи '('
    # (заголовки, речення тощо) — пропускаємо швидко
    if stripped[0].isupper() and "=" not in stripped and "(" not in stripped:
        return False
    try:
        ast.parse(stripped)
        return True
    except SyntaxError:
        return False


_INLINE_ASSIGN_RE = re.compile(
    r"\b([A-Za-z_]\w*)\s*=\s*([A-Za-z_]\w*)\s*\(",
)


def _extract_inline_code_snippets(text: str) -> list[str]:
    """
    Третій етап: витягує inline згадки коду з прози за патерном
    'var = func(' або просто 'func(' всередині речення.

    Повертає список мінімальних Python-рядків виду 'var = func(...)'.
    Аргументи не парсимо — просто замінюємо на () щоб отримати валідний AST.
    """
    snippets = []
    for m in _INLINE_ASSIGN_RE.finditer(text):
        var, func = m.group(1), m.group(2)
        snippets.append(f"{var} = {func}()")
    return snippets


def extract_code_blocks(text: str) -> list[str]:
    """
    Витягує Python-код з тексту трьома способами:
    1. Явні ```python ... ``` блоки
    2. Рядки поза блоками, які парсяться як валідний Python
    3. Inline патерни виду 'var = func(' всередині прозового тексту
    """
    blocks: list[str] = []

    # --- Крок 1: явні ```python``` блоки ---
    for m in _CODE_BLOCK_RE.finditer(text):
        blocks.append(m.group(1))

    # --- Прибираємо явні блоки і LaTeX перед кроками 2 і 3 ---
    bare_text = _CODE_BLOCK_RE.sub("\n", text)
    bare_text = _MATH_BLOCK_RE.sub(" ", bare_text)
    bare_text = _MATH_INLINE_RE.sub(" ", bare_text)

    # --- Крок 2: consecutive рядки що парсяться як Python ---
    current_block: list[str] = []
    for line in bare_text.splitlines():
        if _is_code_line(line):
            current_block.append(line.strip())
        else:
            if current_block:
                blocks.append("\n".join(current_block))
                current_block = []
    if current_block:
        blocks.append("\n".join(current_block))

    # --- Крок 3: inline 'var = func(' патерни з прозових рядків ---
    prose_lines = [line for line in bare_text.splitlines() if not _is_code_line(line)]
    prose = "\n".join(prose_lines)
    inline = _extract_inline_code_snippets(prose)
    if inline:
        blocks.append("\n".join(inline))

    return blocks


# ------------------------------------------------------------------ #
# Lightweight call collector (no definition registration)
# ------------------------------------------------------------------ #


class _CallCollector(ast.NodeVisitor):
    """
    Обходить AST і збирає всі виклики функцій/методів/класів.
    Не реєструє жодних визначень.
    """

    def __init__(self, local_types: dict[str, str] | None = None):
        # var_name -> type_name, заповнюється з присвоєнь у коді прикладу
        self.local_types: dict[str, str] = local_types or {}
        # список (call_name, kind) де kind = "bare" | "method"
        self.calls: list[tuple[str, str]] = []

    def visit_Assign(self, node: ast.Assign) -> None:
        """Трекаємо x = SomeClass(...) щоб потім резолвити x.method()."""
        if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            var = node.targets[0].id
            typ = self._infer_type(node.value)
            if typ:
                self.local_types[var] = typ
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        name, kind = self._resolve(node.func)
        if name:
            self.calls.append((name, kind))
        self.generic_visit(node)

    def _infer_type(self, node: ast.expr) -> str | None:
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            return node.func.id
        return None

    def _resolve(self, node: ast.expr) -> tuple[str | None, str]:
        if isinstance(node, ast.Name):
            return node.id, "bare"

        if isinstance(node, ast.Attribute):
            method = node.attr
            if isinstance(node.value, ast.Name):
                obj = node.value.id
                if obj in EXTERNAL_MODULES:
                    return None, "unknown"
                typ = self.local_types.get(obj)
                if typ:
                    return f"{typ}.{method}", "method"
                return method, "method"

            # deeper chain — find root
            root = self._chain_root(node.value)
            if root in EXTERNAL_MODULES:
                return None, "unknown"
            return method, "method"

        return None, "unknown"

    def _chain_root(self, node: ast.expr) -> str | None:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return self._chain_root(node.value)
        return None


# ------------------------------------------------------------------ #
# Resolve calls against known schema
# ------------------------------------------------------------------ #


def _resolve_calls(
    calls: list[tuple[str, str]],
    known_classes: set[object],
    known_functions: set[object],
    known_methods: set[object],
    local_definitions: set[str],
) -> dict[str, list[str]]:
    """
    Резолвить список (call_name, kind) проти відомих визначень.
    Повертає словник з трьома списками ID.
    """
    # Short-name index for methods: "normalize" -> ["Factor.normalize", ...]
    method_index: dict[str, list[str]] = defaultdict(list)
    for m in known_methods:
        short = str(m).split(".")[-1]
        method_index[short].append(str(m))

    inits: set[str] = set()
    funcs: set[str] = set()
    meths: set[str] = set()

    for call_name, raw_kind in calls:
        parts = call_name.split(".")

        if len(parts) == 2:
            # Qualified: "TypeName.method"
            cls_name, method_name = parts
            qualified = call_name
            if qualified in known_methods:
                meths.add(f"mth:{qualified}")
            else:
                # Try index match
                candidates = [
                    m for m in method_index.get(method_name, []) if m.split(".")[0] == cls_name
                ]
                for c in candidates:
                    meths.add(f"mth:{c}")

        else:
            # Bare name
            short = parts[-1]

            # Skip locally shadowed names
            if short in local_definitions:
                continue

            if short in known_classes:
                inits.add(f"cls:{short}")
            elif short in known_functions:
                funcs.add(f"fn:{short}")
            elif raw_kind == "method":
                candidates = method_index.get(short, [])
                if len(candidates) == 1:
                    meths.add(f"mth:{candidates[0]}")
            # else: ambiguous or unknown — skip

    return {
        "initialized_classes": sorted(inits),
        "used_functions": sorted(funcs),
        "used_methods": sorted(meths),
    }


# ------------------------------------------------------------------ #
# Public API
# ------------------------------------------------------------------ #


def extract_example_refs(
    text: str, schema: dict[str, list[dict[str, object]]]
) -> dict[str, list[str]]:
    """
    Витягує посилання на відомі визначення з тексту прикладу.

    Args:
        text:   рядок з текстом (може містити ```python блоки або bare код)
        schema: результат build_schema() —
                {"classes": [...], "methods": [...], "functions": [...]}

    Returns:
        {"initialized_classes": [...], "used_functions": [...], "used_methods": [...]}
    """
    known_classes = {c["name"] for c in schema["classes"]}
    known_functions = {f["name"] for f in schema["functions"]}
    known_methods = {m["qualified_name"] for m in schema["methods"]}

    blocks = extract_code_blocks(text)
    if not blocks:
        return {"initialized_classes": [], "used_functions": [], "used_methods": []}

    # Збираємо всі виклики з усіх блоків,
    # шерячи local_types між блоками одного прикладу
    collector = _CallCollector()
    local_definitions: set[str] = set()

    for block in blocks:
        try:
            tree = ast.parse(block)
        except SyntaxError:
            continue

        # Збираємо імена функцій/класів визначених прямо в прикладі
        # (щоб не матчити їх проти глобальних визначень)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                local_definitions.add(node.name)

        collector.visit(tree)

    return _resolve_calls(
        collector.calls,
        known_classes,
        known_functions,
        known_methods,
        local_definitions,
    )


# ------------------------------------------------------------------ #
# Entry point
# ------------------------------------------------------------------ #

if __name__ == "__main__":
    import json
    import sys
    from pathlib import Path

    from pipeline.julia_code_translation.build_schema import build_schema

    algorithms_path = sys.argv[1] if len(sys.argv) > 1 else "./translated_algorithms.json"
    examples_path = sys.argv[2] if len(sys.argv) > 2 else "./translated_examples.json"

    with Path(algorithms_path).open() as f:
        algorithms = json.load(f)

    with Path(examples_path).open() as f:
        examples = json.load(f)

    # Будуємо схему з алгоритмів — кожен має "code" і "algorithm_number"
    schema = build_schema(algorithms)
    print(
        f"Schema: {len(schema['classes'])} classes, "
        f"{len(schema['methods'])} methods, "
        f"{len(schema['functions'])} functions\n"
    )

    # Обробляємо кожен приклад
    for example in examples:
        example_number = example.get("example_number", "?")
        text = example.get("text", "")

        blocks = extract_code_blocks(text)
        refs = extract_example_refs(text, schema)

        # Виводимо тільки якщо є хоч якісь посилання
        if any(refs[k] for k in refs):
            print(f"{'='*60}")
            print(f"Example: {example_number}")
            print(f"  Blocks found: {len(blocks)}")
            print(f"  initialized_classes: {refs['initialized_classes']}")
            print(f"  used_functions:      {refs['used_functions']}")
            print(f"  used_methods:        {refs['used_methods']}")
            print()
