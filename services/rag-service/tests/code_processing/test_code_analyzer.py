"""
Unit tests for code_analyzer.py
"""

import ast

from pipeline.code_processing.python_code_processing.code_analyzer import (
    KIND_CLASS_INIT,
    KIND_FUNCTION,
    KIND_METHOD,
    CodeAnalyzer,
    analyze_fragments,
    build_graph,
)

# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #


def _analyze(code: str) -> CodeAnalyzer:
    analyzer = CodeAnalyzer()
    analyzer.visit(ast.parse(code))
    return analyzer


# ------------------------------------------------------------------ #
# Definition registration
# ------------------------------------------------------------------ #


def test_registers_top_level_function():
    analyzer = _analyze("def foo(): pass")
    assert "foo" in analyzer.functions


def test_registers_class():
    analyzer = _analyze("class MyClass: pass")
    assert "MyClass" in analyzer.classes


def test_registers_method():
    analyzer = _analyze("class A:\n    def my_method(self): pass")
    assert "A.my_method" in analyzer.methods


def test_registers_async_function():
    analyzer = _analyze("async def bar(): pass")
    assert "bar" in analyzer.functions


def test_registers_async_method():
    analyzer = _analyze("class B:\n    async def async_method(self): pass")
    assert "B.async_method" in analyzer.methods


def test_class_with_init_registered():
    code = "class C:\n    def __init__(self):\n        self.x = 1"
    analyzer = _analyze(code)
    assert "C" in analyzer.classes
    assert "C.__init__" in analyzer.methods


def test_multiple_classes_registered():
    code = "class X: pass\nclass Y: pass"
    analyzer = _analyze(code)
    assert "X" in analyzer.classes
    assert "Y" in analyzer.classes


def test_fragment_idx_stored_for_function():
    analyzer = CodeAnalyzer()
    analyzer.current_fragment_idx = 42
    analyzer.visit(ast.parse("def foo(): pass"))
    assert analyzer.fragment_idx["foo"] == 42


def test_fragment_idx_stored_for_class():
    analyzer = CodeAnalyzer()
    analyzer.current_fragment_idx = 7
    analyzer.visit(ast.parse("class MyClass: pass"))
    assert analyzer.fragment_idx["MyClass"] == 7


def test_class_updated_when_init_found_later():
    analyzer = CodeAnalyzer()
    analyzer.visit(ast.parse("class C: pass"))
    first_node = analyzer.classes["C"]
    analyzer.visit(ast.parse("class C:\n    def __init__(self): pass"))
    assert analyzer.classes["C"] is not first_node


def test_nested_function_registered_as_local():
    code = "def outer():\n    def inner(): pass"
    analyzer = _analyze(code)
    assert "outer" in analyzer.functions
    assert "inner" in analyzer._local_definitions["outer"]


# ------------------------------------------------------------------ #
# Variable type tracking
# ------------------------------------------------------------------ #


def test_annotated_assignment_tracked():
    code = "x: MyType = MyType()"
    analyzer = _analyze(code)
    assert analyzer.var_types.get("x") == "MyType"


def test_local_annotation_tracked():
    code = "def foo():\n    x: Bar = Bar()"
    analyzer = _analyze(code)
    assert analyzer._local_vars["foo"].get("x") == "Bar"


def test_self_assignment_tracks_class_type():
    code = "class Owner:\n" "    def __init__(self):\n" "        self.helper = Helper()"
    analyzer = _analyze(code)
    assert analyzer._self_attr_types["Owner"].get("helper") == "Helper"


def test_param_annotation_tracked():
    code = "def foo(x: SomeClass): pass"
    analyzer = _analyze(code)
    assert analyzer._local_vars["foo"].get("x") == "SomeClass"


def test_self_param_type_tracked():
    code = "class A:\n    def method(self): pass"
    analyzer = _analyze(code)
    assert analyzer._local_vars["A.method"].get("self") == "A"


# ------------------------------------------------------------------ #
# Call tracking
# ------------------------------------------------------------------ #


def test_bare_function_call_recorded():
    code = "def foo(): pass\ndef bar():\n    foo()"
    analyzer = _analyze(code)
    call_names = [c[0] for c in analyzer.calls["bar"]]
    assert "foo" in call_names


def test_method_call_on_typed_var_resolved():
    code = (
        "class Engine:\n"
        "    def run(self): pass\n"
        "def driver():\n"
        "    e: Engine = Engine()\n"
        "    e.run()"
    )
    analyzer = _analyze(code)
    call_names = [c[0] for c in analyzer.calls["driver"]]
    assert "Engine.run" in call_names


def test_external_module_call_ignored():
    code = "def foo():\n    np.array([1, 2, 3])"
    analyzer = _analyze(code)
    call_names = [c[0] for c in analyzer.calls.get("foo", [])]
    assert all("np" not in (n or "") for n in call_names)


def test_class_instantiation_recorded_as_bare_call():
    code = "class Widget: pass\ndef make():\n    w = Widget()"
    analyzer = _analyze(code)
    call_names = [c[0] for c in analyzer.calls["make"]]
    assert "Widget" in call_names


# ------------------------------------------------------------------ #
# build_graph
# ------------------------------------------------------------------ #


def test_build_graph_function_to_function_edge():
    code = "def helper(): pass\ndef caller():\n    helper()"
    analyzer = _analyze(code)
    graph = build_graph(analyzer)
    assert graph.get("caller", {}).get("helper") == KIND_FUNCTION


def test_build_graph_class_init_edge():
    code = "class Box: pass\ndef factory():\n    b = Box()"
    analyzer = _analyze(code)
    graph = build_graph(analyzer)
    assert graph.get("factory", {}).get("Box") == KIND_CLASS_INIT


def test_build_graph_method_to_method_edge():
    code = (
        "class A:\n" "    def first(self): pass\n" "    def second(self):\n" "        self.first()"
    )
    analyzer = _analyze(code)
    graph = build_graph(analyzer)
    assert graph.get("A.second", {}).get("A.first") == KIND_METHOD


def test_build_graph_unresolved_external_not_present():
    code = "def caller():\n    np.sum([1, 2])"
    analyzer = _analyze(code)
    graph = build_graph(analyzer)
    assert all("np" not in t for t in graph.get("caller", {}))


def test_build_graph_recursive_call_recorded():
    code = "def recursive():\n    recursive()"
    analyzer = _analyze(code)
    graph = build_graph(analyzer)
    assert graph.get("recursive", {}).get("recursive") == KIND_FUNCTION


# ------------------------------------------------------------------ #
# analyze_fragments
# ------------------------------------------------------------------ #


def test_analyze_fragments_plain_string():
    fragments = ["def foo(): pass"]
    analyzer, graph = analyze_fragments(fragments)
    assert "foo" in analyzer.functions


def test_analyze_fragments_dict_with_code_key():
    fragments = [{"code": "def bar(): pass", "algorithm_number": "1.1"}]
    analyzer, graph = analyze_fragments(fragments)
    assert "bar" in analyzer.functions
    assert analyzer.fragment_idx["bar"] == "1.1"


def test_analyze_fragments_dict_missing_algorithm_number_defaults_to_index():
    fragments = [{"code": "def baz(): pass"}]
    analyzer, graph = analyze_fragments(fragments)
    assert analyzer.fragment_idx["baz"] == 0


def test_analyze_fragments_syntax_error_skipped():
    fragments = ["def broken(", "def ok(): pass"]
    analyzer, graph = analyze_fragments(fragments)
    assert "ok" in analyzer.functions


def test_analyze_fragments_multiple_accumulated():
    fragments = [
        "def alpha(): pass",
        "def beta():\n    alpha()",
    ]
    analyzer, graph = analyze_fragments(fragments)
    assert "alpha" in analyzer.functions
    assert "beta" in analyzer.functions
    assert graph.get("beta", {}).get("alpha") == KIND_FUNCTION


def test_analyze_fragments_empty_list():
    analyzer, graph = analyze_fragments([])
    assert not analyzer.functions
    assert not analyzer.classes
    assert not analyzer.methods


def test_analyze_fragments_cross_fragment_references():
    fragments = [
        {"code": "class Engine:\n    def start(self): pass", "algorithm_number": "1"},
        {"code": "def run():\n    e = Engine()\n    e.start()", "algorithm_number": "2"},
    ]
    analyzer, graph = analyze_fragments(fragments)
    assert graph.get("run", {}).get("Engine") == KIND_CLASS_INIT
