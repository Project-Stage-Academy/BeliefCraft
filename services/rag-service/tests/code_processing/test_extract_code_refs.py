"""
Unit tests for extract_code_refs.py
"""

from pipeline.code_processing.python_code_processing.extract_code_refs import (
    SchemaIndex,
    _extract_consecutive_code_lines,
    _extract_fenced_blocks,
    _extract_inline_assignments,
    _is_code_line,
    extract_code_blocks,
    extract_code_refs,
    extract_code_refs_with_index,
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
# _extract_consecutive_code_lines
# ------------------------------------------------------------------ #


def test_extract_consecutive_code_lines_groups_adjacent_code():
    text = "Intro\nx = 1\ny = 2\nMiddle\nfoo()\nEnd"
    blocks = _extract_consecutive_code_lines(text)
    assert blocks == ["x = 1\ny = 2", "foo()"]


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
    assert extract_code_blocks("") == [""]


def test_extract_code_blocks_only_prose_no_crash():
    text = "The algorithm works by iterating over elements."
    blocks = extract_code_blocks(text)
    assert isinstance(blocks, list)


# ------------------------------------------------------------------ #
# SchemaIndex
# ------------------------------------------------------------------ #


def test_schema_index_builds_indexes_from_schema():
    index = SchemaIndex.from_schema(_SAMPLE_SCHEMA)
    assert index.classes == {"Engine", "Wheel"}
    assert index.functions == {"compute", "helper"}
    assert "Engine.start" in index.method_index["start"]


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
    assert set(refs.keys()) == {"referenced_classes", "referenced_functions", "referenced_methods"}


def test_extract_code_refs_empty_text():
    refs = extract_code_refs("", _SAMPLE_SCHEMA)
    assert refs["referenced_classes"] == []
    assert refs["referenced_functions"] == []
    assert refs["referenced_methods"] == []


def test_extract_code_refs_detects_function_call():
    text = "```python\ndef run():\n    compute()\n```"
    refs = extract_code_refs(text, _SAMPLE_SCHEMA)
    assert "fn:compute" in refs["referenced_functions"]


def test_extract_code_refs_detects_class_instantiation():
    text = "```python\ndef run():\n    e = Engine()\n```"
    refs = extract_code_refs(text, _SAMPLE_SCHEMA)
    assert "cls:Engine" in refs["referenced_classes"]


def test_extract_code_refs_detects_method_call():
    text = "```python\ndef run():\n    e = Engine()\n    e.start()\n```"
    refs = extract_code_refs(text, _SAMPLE_SCHEMA)
    assert "mth:Engine.start" in refs["referenced_methods"]


def test_extract_code_refs_unknown_call_not_in_refs():
    text = "```python\ndef run():\n    unknown_func()\n```"
    refs = extract_code_refs(text, _SAMPLE_SCHEMA)
    assert "fn:unknown_func" not in refs["referenced_functions"]


def test_extract_code_refs_sorted_output():
    text = "```python\ndef run():\n    compute()\n    helper()\n```"
    refs = extract_code_refs(text, _SAMPLE_SCHEMA)
    assert refs["referenced_functions"] == sorted(refs["referenced_functions"])


def test_extract_code_refs_locally_defined_not_counted():
    """Functions defined inside the code block should not appear as external refs."""
    text = "```python\ndef compute(): pass\ncompute()\n```"
    refs = extract_code_refs(text, _SAMPLE_SCHEMA)
    assert "fn:compute" not in refs["referenced_functions"]


def test_extract_code_refs_multiple_method_calls():
    text = "```python\ndef run():\n    e = Engine()\n    e.start()\n    e.stop()\n```"
    refs = extract_code_refs(text, _SAMPLE_SCHEMA)
    assert "mth:Engine.start" in refs["referenced_methods"]
    assert "mth:Engine.stop" in refs["referenced_methods"]


def test_extract_code_refs_no_duplicates():
    text = "```python\ndef run():\n    compute()\n    compute()\n```"
    refs = extract_code_refs(text, _SAMPLE_SCHEMA)
    assert len(refs["referenced_functions"]) == len(set(refs["referenced_functions"]))


def test_extract_code_refs_empty_schema():
    schema = {"classes": [], "functions": [], "methods": []}
    text = "```python\ndef run():\n    compute()\n```"
    refs = extract_code_refs(text, schema)
    assert refs["referenced_classes"] == []
    assert refs["referenced_functions"] == []
    assert refs["referenced_methods"] == []


def test_extract_code_refs_prose_with_inline_assignment_no_crash():
    text = "We can write result = compute( to get started."
    refs = extract_code_refs(text, _SAMPLE_SCHEMA)
    assert isinstance(refs["referenced_functions"], list)


def test_extract_code_refs_plain_python_no_fences():
    """Algorithm chunks contain plain Python code without markdown fences."""
    text = "def run():\n    e = Engine()\n    e.start()\n    compute()"
    refs = extract_code_refs(text, _SAMPLE_SCHEMA)
    assert "cls:Engine" in refs["referenced_classes"]
    assert "mth:Engine.start" in refs["referenced_methods"]
    assert "fn:compute" in refs["referenced_functions"]


def test_extract_code_refs_with_index_matches_single_call_api():
    text = "def run():\n    e = Engine()\n    e.stop()\n    helper()"
    index = SchemaIndex.from_schema(_SAMPLE_SCHEMA)
    assert extract_code_refs_with_index(text, index) == extract_code_refs(text, _SAMPLE_SCHEMA)


def test_extract_code_refs_type_hints_create_class_refs_without_constructor_calls():
    text = "def infer(bn: Engine, query: list[str], evidence: Wheel) -> Engine:\n    return bn"
    refs = extract_code_refs(text, _SAMPLE_SCHEMA)
    assert "cls:Engine" in refs["referenced_classes"]
    assert "cls:Wheel" in refs["referenced_classes"]


def test_extract_code_refs_inheritance_adds_parent_reference():
    text = "class Child(Engine):\n    pass"
    refs = extract_code_refs(text, _SAMPLE_SCHEMA)
    assert "cls:Engine" in refs["referenced_classes"]
