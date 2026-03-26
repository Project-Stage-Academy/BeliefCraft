"""
Unit tests for build_code_schema.py
"""

from pipeline.code_processing.python_code_processing.build_code_schema import (
    build_code_schema,
)

# ------------------------------------------------------------------ #
# build_code_schema – structure
# ------------------------------------------------------------------ #


def test_returns_required_keys():
    schema = build_code_schema([])
    assert set(schema.keys()) == {"classes", "methods", "functions"}


def test_empty_input_gives_empty_lists():
    schema = build_code_schema([])
    assert schema["classes"] == []
    assert schema["methods"] == []
    assert schema["functions"] == []


def test_function_record_has_required_fields():
    schema = build_code_schema(["def foo(): pass"])
    record = schema["functions"][0]
    assert "id" in record
    assert "name" in record
    assert "algorithm_number" in record
    assert "code" in record
    assert "referenced_classes" in record
    assert "referenced_functions" in record
    assert "referenced_methods" in record


def test_class_record_has_required_fields():
    schema = build_code_schema(["class MyClass: pass"])
    record = schema["classes"][0]
    assert "id" in record
    assert "name" in record
    assert "algorithm_number" in record
    assert "code" in record


def test_method_record_has_required_fields():
    code = "class A:\n    def greet(self): pass"
    schema = build_code_schema([code])
    record = schema["methods"][0]
    assert "id" in record
    assert "name" in record
    assert "qualified_name" in record
    assert "algorithm_number" in record
    assert "code" in record
    assert "class" in record
    assert "referenced_classes" in record
    assert "referenced_functions" in record
    assert "referenced_methods" in record


# ------------------------------------------------------------------ #
# build_code_schema – function processing
# ------------------------------------------------------------------ #


def test_single_function_id():
    schema = build_code_schema(["def bar(): pass"])
    assert schema["functions"][0]["id"] == "fn:bar"


def test_single_function_name():
    schema = build_code_schema(["def bar(): pass"])
    assert schema["functions"][0]["name"] == "bar"


def test_function_code_is_string():
    schema = build_code_schema(["def bar():\n    return 1"])
    assert isinstance(schema["functions"][0]["code"], str)


def test_function_used_functions_reference():
    fragments = [
        "def helper(): pass",
        "def caller():\n    helper()",
    ]
    schema = build_code_schema(fragments)
    caller = next(f for f in schema["functions"] if f["name"] == "caller")
    assert "fn:helper" in caller["referenced_functions"]


def test_function_referenced_classes_reference():
    fragments = [
        "class Box: pass",
        "def factory():\n    b = Box()",
    ]
    schema = build_code_schema(fragments)
    factory = next(f for f in schema["functions"] if f["name"] == "factory")
    assert "cls:Box" in factory["referenced_classes"]


def test_multiple_functions():
    fragments = ["def alpha(): pass", "def beta(): pass"]
    schema = build_code_schema(fragments)
    names = {f["name"] for f in schema["functions"]}
    assert names == {"alpha", "beta"}


# ------------------------------------------------------------------ #
# build_code_schema – class processing
# ------------------------------------------------------------------ #


def test_simple_class_id():
    schema = build_code_schema(["class Foo: pass"])
    assert len(schema["classes"]) == 1
    assert schema["classes"][0]["id"] == "cls:Foo"


def test_class_with_bases_in_code():
    schema = build_code_schema(["class Parent: pass", "class Child(Parent): pass"])
    child = next(c for c in schema["classes"] if c["name"] == "Child")
    assert "Child(Parent)" in child["code"]


def test_class_with_init_code_contains_init():
    code = "class MyClass:\n" "    def __init__(self, x):\n" "        self.x = x"
    schema = build_code_schema([code])
    class_code = schema["classes"][0]["code"]
    assert "__init__" in class_code


def test_init_method_excluded_from_methods():
    code = "class A:\n" "    def __init__(self): pass\n" "    def method(self): pass"
    schema = build_code_schema([code])
    method_names = [m["name"] for m in schema["methods"]]
    assert "__init__" not in method_names


def test_class_docstring_included_in_code():
    code = "class Documented:\n" '    """A docstring."""\n' "    def __init__(self): pass"
    schema = build_code_schema([code])
    assert "A docstring." in schema["classes"][0]["code"]


# ------------------------------------------------------------------ #
# build_code_schema – method processing
# ------------------------------------------------------------------ #


def test_method_id_format():
    code = "class A:\n    def do(self): pass"
    schema = build_code_schema([code])
    assert schema["methods"][0]["id"] == "mth:A.do"


def test_method_qualified_name():
    code = "class A:\n    def do(self): pass"
    schema = build_code_schema([code])
    assert schema["methods"][0]["qualified_name"] == "A.do"


def test_method_class_ref():
    code = "class A:\n    def do(self): pass"
    schema = build_code_schema([code])
    assert schema["methods"][0]["class"] == "cls:A"


def test_method_used_methods_cross_reference():
    code = (
        "class A:\n" "    def first(self): pass\n" "    def second(self):\n" "        self.first()"
    )
    schema = build_code_schema([code])
    second = next(m for m in schema["methods"] if m["name"] == "second")
    assert "mth:A.first" in second["referenced_methods"]


def test_method_referenced_classes_reference():
    fragments = [
        "class Widget: pass",
        "class Builder:\n    def build(self):\n        w = Widget()",
    ]
    schema = build_code_schema(fragments)
    build_method = next(m for m in schema["methods"] if m["name"] == "build")
    assert "cls:Widget" in build_method["referenced_classes"]


def test_method_known_class_ref_not_external():
    code = "class Known:\n    def do(self): pass"
    schema = build_code_schema([code])
    for m in schema["methods"]:
        assert not m["class"].startswith("external:")


# ------------------------------------------------------------------ #
# build_code_schema – cross-fragment references
# ------------------------------------------------------------------ #


def test_function_references_function_in_another_fragment():
    fragments = [
        "def compute(): pass",
        "def run():\n    compute()",
    ]
    schema = build_code_schema(fragments)
    run = next(f for f in schema["functions"] if f["name"] == "run")
    assert "fn:compute" in run["referenced_functions"]


def test_algorithm_number_populated_from_dict_fragment():
    fragments = [{"code": "def foo(): pass", "algorithm_number": "Algorithm 3.7."}]
    schema = build_code_schema(fragments)
    assert schema["functions"][0]["algorithm_number"] == "3.7"


def test_algorithm_number_empty_for_plain_string_fragment():
    schema = build_code_schema(["def foo(): pass"])
    # Plain string fragments have no algorithm_number; field is present but empty.
    assert schema["functions"][0]["algorithm_number"] == ""


def test_syntax_error_fragment_skipped():
    fragments = ["def broken(", "def good(): pass"]
    schema = build_code_schema(fragments)
    names = {f["name"] for f in schema["functions"]}
    assert "good" in names


def test_no_duplicate_refs():
    """References should be unique even if the callee is called multiple times."""
    fragments = [
        "def helper(): pass",
        "def caller():\n    helper()\n    helper()",
    ]
    schema = build_code_schema(fragments)
    caller = next(f for f in schema["functions"] if f["name"] == "caller")
    assert caller["referenced_functions"].count("fn:helper") == 1


def test_function_referenced_classes_from_param_and_return_type_hints():
    fragments = [
        "class BayesianNetwork: pass",
        "class Assignment: pass",
        "class Factor: pass",
        (
            "def infer(bn: BayesianNetwork, query: list[str], evidence: Assignment) -> Factor:\n"
            "    return Factor()"
        ),
    ]
    schema = build_code_schema(fragments)
    infer_fn = next(f for f in schema["functions"] if f["name"] == "infer")
    # Type hints should create class refs even before runtime calls are considered.
    assert "cls:BayesianNetwork" in infer_fn["referenced_classes"]
    assert "cls:Assignment" in infer_fn["referenced_classes"]
    assert "cls:Factor" in infer_fn["referenced_classes"]


def test_class_with_known_parent_adds_parent_reference():
    fragments = [
        "class Parent: pass",
        "class Child(Parent): pass",
    ]
    schema = build_code_schema(fragments)
    child = next(c for c in schema["classes"] if c["name"] == "Child")
    assert "cls:Parent" in child["referenced_classes"]
