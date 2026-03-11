"""
Unit tests for extract_code_refs.py
"""

import ast

from pipeline.code_processing.python_code_processing.extract_code_refs import (
    _CallCollector,
    _extract_fenced_blocks,
    _extract_inline_assignments,
    _is_code_line,
    _strip_non_code,
    extract_code_blocks,
    extract_code_refs,
)

# ------------------------------------------------------------------ #
# _is_code_line
# ------------------------------------------------------------------ #


def test_is_code_line_empty():
    assert not _is_code_line("")


def test_is_code_line_whitespace():
    assert not _is_code_line("   ")


def test_is_code_line_prose_sentence():
    assert not _is_code_line("The algorithm computes the result.")


def test_is_code_line_simple_assignment():
    assert _is_code_line("x = 1")


def test_is_code_line_function_call():
    assert _is_code_line("foo()")


def test_is_code_line_import():
    assert _is_code_line("import math")


def test_is_code_line_invalid_syntax():
    assert not _is_code_line("def broken(")


# ------------------------------------------------------------------ #
# _extract_fenced_blocks
# ------------------------------------------------------------------ #


def test_extract_fenced_blocks_single():
    text = "```python\ndef foo(): pass\n```"
    blocks = _extract_fenced_blocks(text)
    assert len(blocks) == 1
    assert "def foo(): pass" in blocks[0]


def test_extract_fenced_blocks_multiple():
    text = "```python\ndef a(): pass\n```\nsome prose\n```python\ndef b(): pass\n```"
    blocks = _extract_fenced_blocks(text)
    assert len(blocks) == 2


def test_extract_fenced_blocks_none():
    text = "Plain text without any code blocks."
    assert _extract_fenced_blocks(text) == []


def test_extract_fenced_blocks_non_python_ignored():
    text = "```julia\nfunction f() end\n```"
    assert _extract_fenced_blocks(text) == []


# ------------------------------------------------------------------ #
# _strip_non_code
# ------------------------------------------------------------------ #


def test_strip_non_code_removes_fenced_blocks():
    text = "Before\n```python\ncode\n```\nAfter"
    result = _strip_non_code(text)
    assert "```python" not in result
    assert "code" not in result


def test_strip_non_code_removes_block_math():
    text = "Some text $$x + y = z$$ more text"
    result = _strip_non_code(text)
    assert "$$" not in result


def test_strip_non_code_removes_inline_math():
    text = "Where $x$ is defined"
    result = _strip_non_code(text)
    assert "$x$" not in result


# ------------------------------------------------------------------ #
# _extract_inline_assignments
# ------------------------------------------------------------------ #


def test_extract_inline_assignments_simple():
    text = "We call result = compute("
    snippets = _extract_inline_assignments(text)
    assert any("result = compute()" in s for s in snippets)


def test_extract_inline_assignments_empty():
    text = "No assignments here."
    assert _extract_inline_assignments(text) == []


def test_extract_inline_assignments_multiple():
    text = "a = Foo(\nb = Bar("
    snippets = _extract_inline_assignments(text)
    assert len(snippets) == 2


# ------------------------------------------------------------------ #
# extract_code_blocks
# ------------------------------------------------------------------ #


def test_extract_code_blocks_fenced():
    text = "```python\ndef foo(): pass\n```"
    blocks = extract_code_blocks(text)
    assert any("def foo" in b for b in blocks)


def test_extract_code_blocks_bare_code_lines():
    text = "Here is some prose.\nx = 1\nMore prose."
    blocks = extract_code_blocks(text)
    assert any("x = 1" in b for b in blocks)


def test_extract_code_blocks_empty_text():
    assert extract_code_blocks("") == []


def test_extract_code_blocks_only_prose_no_crash():
    text = "The algorithm works by iterating over elements."
    blocks = extract_code_blocks(text)
    assert isinstance(blocks, list)


# ------------------------------------------------------------------ #
# _CallCollector
# ------------------------------------------------------------------ #


def _collect_from(code: str) -> "_CallCollector":
    tree = ast.parse(code)
    collector = _CallCollector()
    collector.visit(tree)
    return collector


def test_call_collector_bare_function():
    collector = _collect_from("foo()")
    names = [c[0] for c in collector.calls]
    assert "foo" in names


def test_call_collector_method_call():
    collector = _collect_from("obj.method()")
    names = [c[0] for c in collector.calls]
    assert "method" in names


def test_call_collector_external_module_ignored():
    collector = _collect_from("np.array([1, 2])")
    names = [c[0] for c in collector.calls]
    assert all("np" not in (n or "") for n in names)


def test_call_collector_typed_var_resolved():
    code = "obj = MyClass()\nobj.run()"
    collector = _collect_from(code)
    names = [c[0] for c in collector.calls]
    assert "MyClass.run" in names


def test_call_collector_kind_bare_for_simple_call():
    collector = _collect_from("foo()")
    kinds = [c[1] for c in collector.calls]
    assert "bare" in kinds


def test_call_collector_kind_method_for_attribute_call():
    collector = _collect_from("obj.bar()")
    kinds = [c[1] for c in collector.calls]
    assert "method" in kinds


# ------------------------------------------------------------------ #
# extract_code_refs
# ------------------------------------------------------------------ #

_SAMPLE_SCHEMA = {
    "classes": [{"name": "Engine"}, {"name": "Wheel"}],
    "functions": [{"name": "compute"}, {"name": "helper"}],
    "methods": [
        {"qualified_name": "Engine.start"},
        {"qualified_name": "Engine.stop"},
        {"qualified_name": "Wheel.spin"},
    ],
}


def test_extract_code_refs_required_keys():
    refs = extract_code_refs("no code here at all.", _SAMPLE_SCHEMA)
    assert set(refs.keys()) == {"initialized_classes", "referenced_functions", "referenced_methods"}


def test_extract_code_refs_empty_text():
    refs = extract_code_refs("", _SAMPLE_SCHEMA)
    assert refs["initialized_classes"] == []
    assert refs["referenced_functions"] == []
    assert refs["referenced_methods"] == []


def test_extract_code_refs_detects_function_call():
    text = "```python\ncompute()\n```"
    refs = extract_code_refs(text, _SAMPLE_SCHEMA)
    assert "fn:compute" in refs["referenced_functions"]


def test_extract_code_refs_detects_class_instantiation():
    text = "```python\ne = Engine()\n```"
    refs = extract_code_refs(text, _SAMPLE_SCHEMA)
    assert "cls:Engine" in refs["initialized_classes"]


def test_extract_code_refs_detects_method_call():
    text = "```python\ne = Engine()\ne.start()\n```"
    refs = extract_code_refs(text, _SAMPLE_SCHEMA)
    assert "mth:Engine.start" in refs["referenced_methods"]


def test_extract_code_refs_unknown_call_not_in_refs():
    text = "```python\nunknown_func()\n```"
    refs = extract_code_refs(text, _SAMPLE_SCHEMA)
    assert "fn:unknown_func" not in refs["referenced_functions"]


def test_extract_code_refs_sorted_output():
    text = "```python\ncompute()\nhelper()\n```"
    refs = extract_code_refs(text, _SAMPLE_SCHEMA)
    assert refs["referenced_functions"] == sorted(refs["referenced_functions"])


def test_extract_code_refs_locally_defined_not_counted():
    """Functions defined inside the code block should not appear as external refs."""
    text = "```python\ndef compute(): pass\ncompute()\n```"
    refs = extract_code_refs(text, _SAMPLE_SCHEMA)
    assert "fn:compute" not in refs["referenced_functions"]


def test_extract_code_refs_multiple_method_calls():
    text = "```python\n" "e = Engine()\n" "e.start()\n" "e.stop()\n" "```"
    refs = extract_code_refs(text, _SAMPLE_SCHEMA)
    assert "mth:Engine.start" in refs["referenced_methods"]
    assert "mth:Engine.stop" in refs["referenced_methods"]


def test_extract_code_refs_no_duplicates():
    text = "```python\n" "compute()\n" "compute()\n" "```"
    refs = extract_code_refs(text, _SAMPLE_SCHEMA)
    assert len(refs["referenced_functions"]) == len(set(refs["referenced_functions"]))


def test_extract_code_refs_empty_schema():
    schema = {"classes": [], "functions": [], "methods": []}
    text = "```python\ncompute()\n```"
    refs = extract_code_refs(text, schema)
    assert refs["initialized_classes"] == []
    assert refs["referenced_functions"] == []
    assert refs["referenced_methods"] == []


def test_extract_code_refs_prose_with_inline_assignment_no_crash():
    text = "We can write result = compute( to get started."
    refs = extract_code_refs(text, _SAMPLE_SCHEMA)
    assert isinstance(refs["referenced_functions"], list)


def test_extract_code_refs_plain_python_no_fences():
    """Algorithm chunks contain plain Python code without markdown fences."""
    text = "e = Engine()\ne.start()\ncompute()"
    refs = extract_code_refs(text, _SAMPLE_SCHEMA)
    assert "cls:Engine" in refs["initialized_classes"]
    assert "mth:Engine.start" in refs["referenced_methods"]
    assert "fn:compute" in refs["referenced_functions"]
