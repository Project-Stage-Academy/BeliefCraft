"""
extract_example_refs.py
-----------------------
Extracts references to classes, methods, and functions from "examples" —
fragments containing plain text with embedded ```python blocks.

Unlike code_analyzer, no new definitions are registered here;
we only collect calls and resolve them against an already-known schema.

Result:
  {
    "initialized_classes": ["cls:X", ...],
    "used_functions":      ["fn:foo", ...],
    "used_methods":        ["mth:Bar.baz", ...],
  }
"""

import ast
import re
from collections import defaultdict

from common.logging import get_logger
from pipeline.code_processing.python_code_processing.build_code_schema import build_code_schema
from pipeline.code_processing.python_code_processing.constants import EXTERNAL_MODULES

logger = get_logger(__name__)

# ------------------------------------------------------------------ #
# Regex patterns
# ------------------------------------------------------------------ #

_CODE_BLOCK_RE = re.compile(r"```python\s*\n(.*?)```", re.DOTALL)
_MATH_BLOCK_RE = re.compile(r"\$\$.*?\$\$", re.DOTALL)
_MATH_INLINE_RE = re.compile(r"\$[^$]+\$")
_INLINE_ASSIGN_RE = re.compile(r"\b([A-Za-z_]\w*)\s*=\s*([A-Za-z_]\w*)\s*\(")


# ------------------------------------------------------------------ #
# Code block extraction
# ------------------------------------------------------------------ #


def _is_code_line(line: str) -> bool:
    """Heuristic: does this line look like Python code rather than prose."""
    stripped = line.strip()
    if not stripped:
        return False
    if stripped[0].isupper() and "=" not in stripped and "(" not in stripped:
        return False
    try:
        ast.parse(stripped)
        return True
    except SyntaxError:
        return False


def _extract_fenced_blocks(text: str) -> list[str]:
    return [m.group(1) for m in _CODE_BLOCK_RE.finditer(text)]


def _strip_non_code(text: str) -> str:
    text = _CODE_BLOCK_RE.sub("\n", text)
    text = _MATH_BLOCK_RE.sub(" ", text)
    return _MATH_INLINE_RE.sub(" ", text)


def _extract_consecutive_code_lines(text: str) -> list[str]:
    blocks, current = [], []
    for line in text.splitlines():
        if _is_code_line(line):
            current.append(line.strip())
        else:
            if current:
                blocks.append("\n".join(current))
                current = []
    if current:
        blocks.append("\n".join(current))
    return blocks


def _extract_inline_assignments(text: str) -> list[str]:
    """Extract inline 'var = func(' patterns from prose and return minimal valid snippets."""
    return [f"{m.group(1)} = {m.group(2)}()" for m in _INLINE_ASSIGN_RE.finditer(text)]


def extract_code_blocks(text: str) -> list[str]:
    """
    Extract Python code from text in three passes:
    1. Explicit ```python ... ``` fenced blocks.
    2. Consecutive lines outside blocks that parse as valid Python.
    3. Inline 'var = func(' patterns in prose.
    """
    blocks = _extract_fenced_blocks(text)

    bare_text = _strip_non_code(text)
    blocks.extend(_extract_consecutive_code_lines(bare_text))

    prose_lines = [line for line in bare_text.splitlines() if not _is_code_line(line)]
    inline = _extract_inline_assignments("\n".join(prose_lines))
    if inline:
        blocks.append("\n".join(inline))

    return blocks


# ------------------------------------------------------------------ #
# Lightweight call collector
# ------------------------------------------------------------------ #


class _CallCollector(ast.NodeVisitor):
    """Traverse AST and collect all function/method/class calls without registering definitions."""

    def __init__(self, local_types: dict[str, str] | None = None):
        self.local_types: dict[str, str] = local_types or {}
        self.calls: list[tuple[str, str]] = []

    def visit_Assign(self, node: ast.Assign) -> None:
        if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            typ = self._infer_type(node.value)
            if typ:
                self.local_types[node.targets[0].id] = typ
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
            return self._resolve_attribute(node)
        return None, "unknown"

    def _resolve_attribute(self, node: ast.Attribute) -> tuple[str | None, str]:
        method = node.attr
        if isinstance(node.value, ast.Name):
            obj = node.value.id
            if obj in EXTERNAL_MODULES:
                return None, "unknown"
            typ = self.local_types.get(obj)
            return (f"{typ}.{method}" if typ else method), "method"
        root = self._chain_root(node.value)
        if root in EXTERNAL_MODULES:
            return None, "unknown"
        return method, "method"

    def _chain_root(self, node: ast.expr) -> str | None:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return self._chain_root(node.value)
        return None


# ------------------------------------------------------------------ #
# Resolve calls against known schema
# ------------------------------------------------------------------ #


def _build_method_index(known_methods: set[object]) -> dict[str, list[str]]:
    index: dict[str, list[str]] = defaultdict(list)
    for m in known_methods:
        index[str(m).split(".")[-1]].append(str(m))
    return index


def _resolve_qualified_call(
    call_name: str,
    known_methods: set[object],
    method_index: dict[str, list[str]],
) -> list[str]:
    cls_name, method_name = call_name.split(".", 1)
    if call_name in known_methods:
        return [f"mth:{call_name}"]
    candidates = [m for m in method_index.get(method_name, []) if m.split(".")[0] == cls_name]
    return [f"mth:{c}" for c in candidates]


def _resolve_bare_call(
    call_name: str,
    raw_kind: str,
    known_classes: set[object],
    known_functions: set[object],
    method_index: dict[str, list[str]],
    local_definitions: set[str],
) -> tuple[str | None, str | None, str | None]:
    """Return (cls_ref, fn_ref, mth_ref) — at most one will be set."""
    short = call_name.split(".")[-1]
    if short in local_definitions:
        return None, None, None
    if short in known_classes:
        return f"cls:{short}", None, None
    if short in known_functions:
        return None, f"fn:{short}", None
    if raw_kind == "method":
        candidates = method_index.get(short, [])
        if len(candidates) == 1:
            return None, None, f"mth:{candidates[0]}"
    return None, None, None


def _resolve_calls(
    calls: list[tuple[str, str]],
    known_classes: set[object],
    known_functions: set[object],
    known_methods: set[object],
    local_definitions: set[str],
) -> dict[str, list[str]]:
    method_index = _build_method_index(known_methods)
    inits: set[str] = set()
    funcs: set[str] = set()
    meths: set[str] = set()

    for call_name, raw_kind in calls:
        if len(call_name.split(".")) == 2:
            meths.update(_resolve_qualified_call(call_name, known_methods, method_index))
        else:
            cls_ref, fn_ref, mth_ref = _resolve_bare_call(
                call_name, raw_kind, known_classes, known_functions, method_index, local_definitions
            )
            if cls_ref:
                inits.add(cls_ref)
            if fn_ref:
                funcs.add(fn_ref)
            if mth_ref:
                meths.add(mth_ref)

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
    Extract references to known definitions from an example text.

    Args:
        text:   string with text (may contain ```python blocks or bare code)
        schema: result of build_code_schema() —
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

    collector = _CallCollector()
    local_definitions: set[str] = set()

    for block in blocks:
        try:
            tree = ast.parse(block)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                local_definitions.add(node.name)
        collector.visit(tree)

    return _resolve_calls(
        collector.calls, known_classes, known_functions, known_methods, local_definitions
    )


if __name__ == "__main__":
    import json
    import sys
    from pathlib import Path

    algorithms_path = sys.argv[1] if len(sys.argv) > 1 else "./translated_algorithms.json"
    examples_path = sys.argv[2] if len(sys.argv) > 2 else "./translated_examples.json"

    with Path(algorithms_path).open() as f:
        algorithms = json.load(f)
    with Path(examples_path).open() as f:
        examples = json.load(f)

    schema = build_code_schema(algorithms)
    logger.info(
        "Schema: %d classes, %d methods, %d functions",
        len(schema["classes"]),
        len(schema["methods"]),
        len(schema["functions"]),
    )

    for example in examples:
        example_number = example.get("example_number", "?")
        text = example.get("text", "")
        refs = extract_example_refs(text, schema)

        if any(refs[k] for k in refs):
            logger.info("Example: %s", example_number)
            logger.info("  Blocks found:        %d", len(extract_code_blocks(text)))
            logger.info("  initialized_classes: %s", refs["initialized_classes"])
            logger.info("  used_functions:      %s", refs["used_functions"])
            logger.info("  used_methods:        %s", refs["used_methods"])
