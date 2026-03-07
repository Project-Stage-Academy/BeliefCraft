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
from dataclasses import dataclass, field

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
# Schema index
# ------------------------------------------------------------------ #


@dataclass
class SchemaIndex:
    """Pre-built lookup structures derived from a code schema."""

    classes: set[str] = field(default_factory=set)
    functions: set[str] = field(default_factory=set)
    methods: set[str] = field(default_factory=set)
    method_index: dict[str, list[str]] = field(default_factory=dict)

    @classmethod
    def from_schema(cls, schema: dict[str, list[dict[str, object]]]) -> "SchemaIndex":
        """Build a SchemaIndex from the result of build_code_schema()."""
        classes: set[str] = {str(c["name"]) for c in schema["classes"]}
        functions: set[str] = {str(f["name"]) for f in schema["functions"]}
        methods: set[str] = {str(m["qualified_name"]) for m in schema["methods"]}
        method_index = _build_method_index(methods)
        return cls(classes=classes, functions=functions, methods=methods, method_index=method_index)


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
    """Return the contents of fenced ```python blocks found in the text."""
    return [m.group(1) for m in _CODE_BLOCK_RE.finditer(text)]


def _strip_non_code(text: str) -> str:
    """Remove fenced code and math blocks/inline math from text."""
    text = _CODE_BLOCK_RE.sub("\n", text)
    text = _MATH_BLOCK_RE.sub(" ", text)
    return _MATH_INLINE_RE.sub(" ", text)


def _extract_consecutive_code_lines(text: str) -> list[str]:
    """Collect consecutive lines that look like code into code blocks."""
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
    blocks: list[str] = []

    # Pass 1: fenced python blocks
    fenced = _extract_fenced_blocks(text)
    blocks.extend(fenced)

    # Remove fenced blocks from the working text to avoid overlap with later passes
    working = _CODE_BLOCK_RE.sub("\n", text)

    # Pass 2: consecutive lines that look like code in the remaining text
    consecutive = _extract_consecutive_code_lines(working)
    blocks.extend(consecutive)

    # Remove the consecutive code lines from the working text so inline extraction
    # won't pick up the same code again. We remove by line (matching stripped form).
    if consecutive:
        code_line_set = {line for block in consecutive for line in block.splitlines()}
        new_lines: list[str] = []
        for line in working.splitlines():
            if _is_code_line(line) and line.strip() in code_line_set:
                new_lines.append("")
            else:
                new_lines.append(line)
        working = "\n".join(new_lines)

    # Pass 3: inline assignments from the remaining prose-only lines
    prose_lines = [line for line in working.splitlines() if not _is_code_line(line)]
    inline = _extract_inline_assignments("\n".join(prose_lines))
    if inline:
        blocks.append("\n".join(inline))

    return blocks


# ------------------------------------------------------------------ #
# Lightweight call collector
# ------------------------------------------------------------------ #


class _CallCollector(ast.NodeVisitor):
    """Traverse an AST and collect all function/method/class calls.

    Does not register any definitions — only collects call sites for later
    resolution against a known schema.
    """

    def __init__(self, local_types: dict[str, str] | None = None):
        # Maps variable name -> inferred class name, e.g. {"foo": "Foo"} after `foo = Foo()`.
        self.local_types: dict[str, str] = local_types or {}
        self.calls: list[tuple[str, str]] = []

    def visit_Assign(self, node: ast.Assign) -> None:
        """Record the inferred type of a variable when it is assigned from a constructor call."""
        if len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name):
                typ = self._infer_type(node.value)
                if typ:
                    self.local_types[target.id] = typ
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        """Collect (name, kind) for every Call node in the tree."""
        name, kind = self._resolve(node.func)
        if name:
            self.calls.append((name, kind))
        self.generic_visit(node)

    def _infer_type(self, node: ast.expr) -> str | None:
        """Return the called class name for a bare constructor call, e.g. ``Foo()`` → ``'Foo'``."""
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            return node.func.id
        return None

    def _resolve(self, node: ast.expr) -> tuple[str | None, str]:
        """Resolve a call target expression to a (name, kind) pair.

        kind is one of ``"bare"`` (plain name) or ``"method"`` (attribute access).
        Returns ``(None, "unknown")`` for unresolvable nodes.
        """
        if isinstance(node, ast.Name):
            return node.id, "bare"
        if isinstance(node, ast.Attribute):
            return self._resolve_attribute(node)
        return None, "unknown"

    def _resolve_attribute(self, node: ast.Attribute) -> tuple[str | None, str]:
        """Resolve an attribute call to a method name, qualifying it when the receiver type is known

        Calls on known external modules (e.g. ``np.array``) are ignored and
        return ``(None, "unknown")``.

        Examples::

            foo.bar()          # local_types has no entry for foo  →  ("bar",       "method")
            foo.bar()          # local_types["foo"] == "Foo"       →  ("Foo.bar",   "method")
            np.array()         # np in EXTERNAL_MODULES            →  (None,        "unknown")
        """
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
        """Return the leftmost name in a dotted chain (``a.b.c`` → ``"a"``), or ``None``."""
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return self._chain_root(node.value)
        return None


# ------------------------------------------------------------------ #
# Resolve calls against known schema
# ------------------------------------------------------------------ #


def _build_method_index(known_methods: set[str]) -> dict[str, list[str]]:
    """Build an index mapping unqualified method names to fully-qualified candidates.

    Example: ``{"baz": ["Bar.baz", "Qux.baz"]}``
    """
    index: dict[str, list[str]] = defaultdict(list)
    for m in known_methods:
        index[str(m).split(".")[-1]].append(str(m))
    return index


def _resolve_dotted_method_call(call_name: str, index: SchemaIndex) -> list[str]:
    """Resolve a ``Class.method`` call string to a list of matching ``mth:`` refs.

    First tries an exact match in the schema; if that fails, falls back to
    candidates where the class name prefix matches.
    """
    cls_name, method_name = call_name.split(".", 1)
    if call_name in index.methods:
        return [f"mth:{call_name}"]
    candidates = [m for m in index.method_index.get(method_name, []) if m.split(".")[0] == cls_name]
    return [f"mth:{c}" for c in candidates]


def _resolve_unqualified_call(
    call_name: str,
    kind: str,
    index: SchemaIndex,
    local_definitions: set[str],
) -> str | None:
    """Map a single unqualified call to a schema ref string, or ``None`` if unrecognised.

    Resolution priority:
    1. Skip names defined locally in the same code block.
    2. Class instantiation  → ``"cls:<name>"``
    3. Module-level function → ``"fn:<name>"``
    4. Unqualified method (``kind == "method"``) with exactly one candidate → ``"mth:<Class.name>"``

    Returns ``None`` when the call cannot be mapped to any known definition.
    """
    if call_name in local_definitions:
        return None
    if call_name in index.classes:
        return f"cls:{call_name}"
    if call_name in index.functions:
        return f"fn:{call_name}"
    if kind == "method":
        candidates = index.method_index.get(call_name, [])
        if len(candidates) == 1:
            return f"mth:{candidates[0]}"
    return None


def _resolve_calls(
    calls: list[tuple[str, str]],
    index: SchemaIndex,
    local_definitions: set[str],
) -> dict[str, list[str]]:
    """Resolve collected (name, kind) call pairs against the known schema.

    Returns a dict with three sorted lists of ref strings::

        {
            "initialized_classes": ["cls:Foo", ...],
            "used_functions":      ["fn:bar", ...],
            "used_methods":        ["mth:Baz.qux", ...],
        }
    """
    inits: set[str] = set()
    funcs: set[str] = set()
    meths: set[str] = set()

    for call_name, kind in calls:
        if "." in call_name:
            meths.update(_resolve_dotted_method_call(call_name, index))
        else:
            ref = _resolve_unqualified_call(call_name, kind, index, local_definitions)
            if ref is None:
                pass
            elif ref.startswith("cls:"):
                inits.add(ref)
            elif ref.startswith("fn:"):
                funcs.add(ref)
            elif ref.startswith("mth:"):
                meths.add(ref)

    return {
        "initialized_classes": sorted(inits),
        "used_functions": sorted(funcs),
        "used_methods": sorted(meths),
    }


# ------------------------------------------------------------------ #
# Public API
# ------------------------------------------------------------------ #


def extract_example_refs_with_index(
    text: str,
    index: SchemaIndex,
) -> dict[str, list[str]]:
    """Extract schema refs from *text* using a pre-built ``SchemaIndex``.

    Prefer this over :func:`extract_example_refs` in hot paths where the same
    schema is reused across many examples.
    """
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

    return _resolve_calls(collector.calls, index, local_definitions)


def extract_example_refs(
    text: str, schema: dict[str, list[dict[str, object]]]
) -> dict[str, list[str]]:
    """Extract references to known definitions from an example text.

    Builds a :class:`SchemaIndex` from *schema* on every call. When processing
    many examples against the same schema, use
    :func:`extract_example_refs_with_index` with a shared index instead.

    Args:
        text:   String with prose and optional ``python`` code blocks.
        schema: Result of ``build_code_schema()`` —
                ``{"classes": [...], "methods": [...], "functions": [...]}``.

    Returns:
        ``{"initialized_classes": [...], "used_functions": [...], "used_methods": [...]}``.
    """
    return extract_example_refs_with_index(text, SchemaIndex.from_schema(schema))


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

    index = SchemaIndex.from_schema(schema)

    for example in examples:
        example_number = example.get("example_number", "?")
        text = example.get("text", "")
        refs = extract_example_refs_with_index(text, index)

        if any(refs[k] for k in refs):
            logger.info("Example: %s", example_number)
            logger.info("  Blocks found:        %d", len(extract_code_blocks(text)))
            logger.info("  initialized_classes: %s", refs["initialized_classes"])
            logger.info("  used_functions:      %s", refs["used_functions"])
            logger.info("  used_methods:        %s", refs["used_methods"])
