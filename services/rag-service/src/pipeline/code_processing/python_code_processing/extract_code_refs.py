"""
extract_code_refs.py
--------------------
Extracts references to classes, methods, and functions from code chunks —
algorithm or example fragments containing Python code (plain or embedded in
```python blocks inside prose).

Unlike code_analyzer, no new definitions are registered here;
we only collect calls and resolve them against an already-known schema.

Result:
  {
    "referenced_classes":   ["cls:X", ...],
    "referenced_functions": ["fn:foo", ...],
    "referenced_methods":   ["mth:Bar.baz", ...],
  }
"""

import ast
import re
from collections import defaultdict
from dataclasses import dataclass, field

from common.logging import get_logger
from pipeline.code_processing.python_code_processing.build_code_schema import build_code_schema
from pipeline.code_processing.python_code_processing.code_analyzer import (
    KIND_CLASS_INIT,
    KIND_FUNCTION,
    KIND_METHOD,
    CodeAnalyzer,
    analyze_fragments,
)

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
        index: dict[str, list[str]] = defaultdict(list)
        for m in methods:
            index[m.split(".")[-1]].append(m)
        return cls(classes=classes, functions=functions, methods=methods, method_index=index)


# ------------------------------------------------------------------ #
# Code block extraction
# ------------------------------------------------------------------ #


def _is_code_line(line: str) -> bool:
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
    return [f"{m.group(1)} = {m.group(2)}()" for m in _INLINE_ASSIGN_RE.finditer(text)]


def extract_code_blocks(text: str) -> list[str]:
    """
    Extract Python code from text in up to four passes:
    0. Whole text parses as valid Python → return it directly.
    1. Explicit ```python ... ``` fenced blocks.
    2. Consecutive lines outside blocks that parse as valid Python.
    3. Inline 'var = func(' patterns in prose.
    """
    # Pass 0: entire text is valid Python (plain algorithm chunks)
    try:
        ast.parse(text)
        return [text]
    except SyntaxError:
        pass

    blocks: list[str] = []

    # Pass 1: fenced python blocks
    fenced = _extract_fenced_blocks(text)
    blocks.extend(fenced)

    # if fenced blocks found — skip consecutive/inline to avoid duplication
    if fenced:
        return blocks

    working = _CODE_BLOCK_RE.sub("\n", text)
    consecutive = _extract_consecutive_code_lines(working)
    blocks.extend(consecutive)

    if consecutive:
        code_line_set = {line for block in consecutive for line in block.splitlines()}
        new_lines: list[str] = []
        for line in working.splitlines():
            if _is_code_line(line) and line.strip() in code_line_set:
                new_lines.append("")
            else:
                new_lines.append(line)
        working = "\n".join(new_lines)

    prose_lines = [line for line in working.splitlines() if not _is_code_line(line)]
    inline = _extract_inline_assignments("\n".join(prose_lines))
    if inline:
        blocks.append("\n".join(inline))

    return blocks


# ------------------------------------------------------------------ #
# Core resolution
# ------------------------------------------------------------------ #


_Refs = tuple[set[str], set[str], set[str]]  # (classes, functions, methods)


def _collect_from_graph(
    graph: dict[str, dict[str, str]],
    index: SchemaIndex,
    local_classes: set[str],
    local_functions: set[str],
    local_methods: set[str],
) -> _Refs:
    """Pass 1: graph edges between local definitions → external schema entries."""
    classes: set[str] = set()
    functions: set[str] = set()
    methods: set[str] = set()
    for edges in graph.values():
        for target, kind in edges.items():
            if kind == KIND_CLASS_INIT and target not in local_classes and target in index.classes:
                classes.add(f"cls:{target}")
            elif (
                kind == KIND_FUNCTION
                and target not in local_functions
                and target in index.functions
            ):
                functions.add(f"fn:{target}")
            elif kind == KIND_METHOD and target not in local_methods and target in index.methods:
                methods.add(f"mth:{target}")
    return classes, functions, methods


def _resolve_dotted_call(
    qualified: str,
    method_name: str,
    index: SchemaIndex,
    local_methods: set[str],
    methods: set[str],
) -> None:
    """Resolve a ``Class.method`` call into *methods*."""
    if qualified in index.methods and qualified not in local_methods:
        methods.add(f"mth:{qualified}")
    else:
        for candidate in index.method_index.get(method_name, []):
            if candidate not in local_methods:
                methods.add(f"mth:{candidate}")


def _resolve_bare_call(
    short: str,
    raw_kind: str,
    index: SchemaIndex,
    local_classes: set[str],
    local_functions: set[str],
    local_methods: set[str],
    classes: set[str],
    functions: set[str],
    methods: set[str],
) -> None:
    """Resolve an unqualified call name into the appropriate ref set."""
    if short in local_classes or short in local_functions:
        return
    if short in index.classes:
        classes.add(f"cls:{short}")
    elif short in index.functions:
        functions.add(f"fn:{short}")
    elif raw_kind == "method":
        for candidate in index.method_index.get(short, []):
            if candidate not in local_methods:
                methods.add(f"mth:{candidate}")


def _collect_from_raw_calls(
    analyzer: CodeAnalyzer,
    index: SchemaIndex,
    local_classes: set[str],
    local_functions: set[str],
    local_methods: set[str],
) -> _Refs:
    """Pass 2: raw calls resolved directly against the index.

    Catches external definitions not present in the blocks (e.g. functions
    defined in other algorithm chunks).
    """
    classes: set[str] = set()
    functions: set[str] = set()
    methods: set[str] = set()
    for calls in analyzer.calls.values():
        for call_name, _argc, raw_kind in calls:
            parts = call_name.split(".")
            if len(parts) == 2:
                _resolve_dotted_call(call_name, parts[1], index, local_methods, methods)
            else:
                _resolve_bare_call(
                    parts[-1],
                    raw_kind,
                    index,
                    local_classes,
                    local_functions,
                    local_methods,
                    classes,
                    functions,
                    methods,
                )
    return classes, functions, methods


def _collect_from_bases(analyzer: CodeAnalyzer, index: SchemaIndex) -> set[str]:
    """Pass 3: base class inheritance → external class refs."""
    classes: set[str] = set()
    for cls_node in analyzer.classes.values():
        for base in cls_node.bases:
            if isinstance(base, ast.Name) and base.id in index.classes:
                classes.add(f"cls:{base.id}")
    return classes


def _collect_from_annotations(
    analyzer: CodeAnalyzer,
    index: SchemaIndex,
    local_classes: set[str],
) -> set[str]:
    """Pass 4: parameter type annotations and return types → external class refs."""
    classes: set[str] = set()
    for local_vars in analyzer._local_vars.values():
        for var, typ in local_vars.items():
            if var not in ("self", "cls") and typ in index.classes and typ not in local_classes:
                classes.add(f"cls:{typ}")
    for ret_type in analyzer._return_types.values():
        if ret_type in index.classes and ret_type not in local_classes:
            classes.add(f"cls:{ret_type}")
    return classes


def _refs_from_blocks(blocks: list[str], index: SchemaIndex) -> dict[str, list[str]]:
    """Analyze code blocks and resolve calls against the known schema index."""
    analyzer, graph = analyze_fragments(blocks)

    local_classes: set[str] = set(analyzer.classes)
    local_functions: set[str] = set(analyzer.functions)
    local_methods: set[str] = set(analyzer.methods)

    cls1, fn1, mth1 = _collect_from_graph(
        graph, index, local_classes, local_functions, local_methods
    )
    cls2, fn2, mth2 = _collect_from_raw_calls(
        analyzer, index, local_classes, local_functions, local_methods
    )
    cls3 = _collect_from_bases(analyzer, index)
    cls4 = _collect_from_annotations(analyzer, index, local_classes)

    return {
        "referenced_classes": sorted(cls1 | cls2 | cls3 | cls4),
        "referenced_functions": sorted(fn1 | fn2),
        "referenced_methods": sorted(mth1 | mth2),
    }


# ------------------------------------------------------------------ #
# Public API
# ------------------------------------------------------------------ #


def extract_code_refs_with_index(
    text: str,
    index: SchemaIndex,
) -> dict[str, list[str]]:
    """Extract schema refs from *text* using a pre-built ``SchemaIndex``.

    Prefer this over :func:`extract_code_refs` in hot paths where the same
    schema is reused across many chunks.
    """
    blocks = extract_code_blocks(text)
    if not blocks:
        return {"referenced_classes": [], "referenced_functions": [], "referenced_methods": []}
    return _refs_from_blocks(blocks, index)


def extract_code_refs(
    text: str, schema: dict[str, list[dict[str, object]]]
) -> dict[str, list[str]]:
    """Extract references to known definitions from a code chunk text.

    Works for both algorithm chunks (plain Python code) and example chunks
    (prose with embedded ``python`` code blocks). Builds a :class:`SchemaIndex`
    from *schema* on every call. When processing many chunks against the same
    schema, use :func:`extract_code_refs_with_index` with a shared index instead.
    """
    return extract_code_refs_with_index(text, SchemaIndex.from_schema(schema))


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
        refs = extract_code_refs_with_index(text, index)

        if any(refs[k] for k in refs):
            logger.info("Example: %s", example_number)
            logger.info("  Blocks found:           %d", len(extract_code_blocks(text)))
            logger.info("  referenced_classes:     %s", refs["referenced_classes"])
            logger.info("  referenced_functions:   %s", refs["referenced_functions"])
            logger.info("  referenced_methods:     %s", refs["referenced_methods"])
