"""
Tests for CodeDefinitionProcessor — graph traversal and source reconstruction.

These tests use lightweight mock Weaviate objects so no real DB connection is needed.
"""

from unittest.mock import MagicMock

from rag_service.code_entity_processor import WeaviateCodeDefinitionProcessor
from rag_service.models import Document

# ------------------------------------------------------------------ #
# Helpers to build mock Weaviate objects                              #
# ------------------------------------------------------------------ #


def _make_ref(objects):
    """Wrap a list of mock objects into a reference-like container."""
    ref = MagicMock()
    ref.objects = objects
    return ref


def _make_weaviate_obj(uuid, collection, properties, references=None):
    """Create a minimal Weaviate object mock."""
    obj = MagicMock()
    obj.uuid = uuid
    obj.collection = collection
    obj.properties = properties
    obj.references = references or {}
    return obj


# ------------------------------------------------------------------ #
# Test data                                                           #
# ------------------------------------------------------------------ #

CLASS_UUID = "cls-uuid-001"
METHOD_UUID = "mth-uuid-001"
FUNCTION_UUID = "fn-uuid-001"
CALLEE_FN_UUID = "fn-uuid-002"
ALGORITH_UUID = "alg-uuid-001"

CLASS_CONTENT = "class Foo:\n    def __init__(self, x):\n        self.x = x"
METHOD_CONTENT = "def bar(self):\n    return self.x"
FUNCTION_CONTENT = "def helper():\n    return 42"
CALLEE_CONTENT = "def callee():\n    pass"


def _class_obj():
    return _make_weaviate_obj(
        uuid=CLASS_UUID,
        collection="CodeClass",
        properties={"name": "Foo", "schema_id": "cls:Foo", "content": CLASS_CONTENT},
    )


def _method_obj():
    class_ref = _make_ref([_class_obj()])
    return _make_weaviate_obj(
        uuid=METHOD_UUID,
        collection="CodeMethod",
        properties={
            "name": "bar",
            "schema_id": "mth:Foo.bar",
            "content": METHOD_CONTENT,
            "qualified_name": "Foo.bar",
        },
        references={"class_ref": class_ref},
    )


def _function_obj(uuid=FUNCTION_UUID, content=FUNCTION_CONTENT, refs=None):
    return _make_weaviate_obj(
        uuid=uuid,
        collection="CodeFunction",
        properties={"name": "helper", "schema_id": "fn:helper", "content": content},
        references=refs or {},
    )


# ------------------------------------------------------------------ #
# collect_code_definitions                                            #
# ------------------------------------------------------------------ #


class TestCollectCodeDefinitions:
    """Tests for CodeDefinitionProcessor.collect_code_definitions."""

    def test_collects_standalone_function(self):
        fn = _function_obj()
        root = _make_weaviate_obj(
            uuid="root-001",
            collection="unified_collection",
            properties={},
            references={"referenced_functions": _make_ref([fn])},
        )
        docs = WeaviateCodeDefinitionProcessor.collect_code_definitions([root], [ALGORITH_UUID])

        assert len(docs) == 1
        assert docs[0].id == FUNCTION_UUID
        assert docs[0].content == FUNCTION_CONTENT

    def test_collects_method_with_its_class(self):
        method = _method_obj()
        root = _make_weaviate_obj(
            uuid="root-002",
            collection="unified_collection",
            properties={},
            references={"referenced_methods": _make_ref([method])},
        )
        docs = WeaviateCodeDefinitionProcessor.collect_code_definitions([root], [ALGORITH_UUID])

        # Expect: class emitted before method
        ids = [d.id for d in docs]
        assert CLASS_UUID in ids
        assert METHOD_UUID in ids
        assert ids.index(CLASS_UUID) < ids.index(METHOD_UUID)

    def test_class_content_preserved(self):
        method = _method_obj()
        root = _make_weaviate_obj(
            uuid="root-003",
            collection="unified_collection",
            properties={},
            references={"referenced_methods": _make_ref([method])},
        )
        docs = WeaviateCodeDefinitionProcessor.collect_code_definitions([root], [ALGORITH_UUID])

        class_doc = next(d for d in docs if d.id == CLASS_UUID)
        assert class_doc.content == CLASS_CONTENT

    def test_deduplicates_across_roots(self):
        fn = _function_obj()
        root1 = _make_weaviate_obj(
            uuid="root-004",
            collection="unified_collection",
            properties={},
            references={"referenced_functions": _make_ref([fn])},
        )
        root2 = _make_weaviate_obj(
            uuid="root-005",
            collection="unified_collection",
            properties={},
            references={"referenced_functions": _make_ref([fn])},
        )
        docs = WeaviateCodeDefinitionProcessor.collect_code_definitions(
            [root1, root2], [ALGORITH_UUID]
        )

        ids = [d.id for d in docs]
        assert ids.count(FUNCTION_UUID) == 1

    def test_callee_placed_before_caller(self):
        """Callee function referenced inside helper must appear before helper."""
        callee = _function_obj(uuid=CALLEE_FN_UUID, content=CALLEE_CONTENT)
        caller = _function_obj(
            uuid=FUNCTION_UUID,
            content=FUNCTION_CONTENT,
            refs={"referenced_functions": _make_ref([callee])},
        )
        root = _make_weaviate_obj(
            uuid="root-006",
            collection="unified_collection",
            properties={},
            references={"referenced_functions": _make_ref([caller])},
        )
        docs = WeaviateCodeDefinitionProcessor.collect_code_definitions([root], [ALGORITH_UUID])

        ids = [d.id for d in docs]
        assert ids.index(CALLEE_FN_UUID) < ids.index(FUNCTION_UUID)

    def test_returns_empty_for_no_references(self):
        root = _make_weaviate_obj(
            uuid="root-007",
            collection="unified_collection",
            properties={},
            references={},
        )
        docs = WeaviateCodeDefinitionProcessor.collect_code_definitions([root], [ALGORITH_UUID])
        assert docs == []


# ------------------------------------------------------------------ #
# restore_code_fragment                                               #
# ------------------------------------------------------------------ #


class TestRestoreCodeFragment:
    """Tests for CodeDefinitionProcessor.restore_code_fragment."""

    def _make_fn_doc(self, uid, content, collection="CodeFunction"):
        return Document(
            id=uid,
            content=content,
            metadata={"collection": collection, "name": f"fn_{uid}"},
        )

    def _make_class_doc(self, uid, name, content):
        return Document(
            id=uid,
            content=content,
            metadata={"collection": "CodeClass", "name": name},
        )

    def _make_method_doc(self, uid, content, class_name):
        return Document(
            id=uid,
            content=content,
            metadata={"collection": "CodeMethod", "name": f"mth_{uid}", "class_name": class_name},
        )

    def test_single_function(self):
        docs = [self._make_fn_doc("f1", "def foo():\n    pass")]
        result = WeaviateCodeDefinitionProcessor.restore_code_fragment(docs)
        assert "def foo():" in result

    def test_class_with_init_and_method(self):
        class_doc = self._make_class_doc(
            "c1",
            "Bar",
            "class Bar:\n    def __init__(self):\n        self.x = 0",
        )
        method_doc = self._make_method_doc(
            "m1",
            "def compute(self):\n    return self.x * 2",
            "Bar",
        )
        docs = [class_doc, method_doc]
        result = WeaviateCodeDefinitionProcessor.restore_code_fragment(docs)

        # Class header with __init__ must be present
        assert "class Bar:" in result
        assert "def __init__" in result
        # Method must be present and indented inside the class block
        assert "def compute(self):" in result
        # The whole thing should be one block (method is part of class, not separate)
        assert result.count("class Bar:") == 1

    def test_no_duplicate_fragments(self):
        doc = self._make_fn_doc("f1", "def foo():\n    pass")
        # Pass duplicates
        docs = [doc, doc]
        result = WeaviateCodeDefinitionProcessor.restore_code_fragment(docs)
        assert result.count("def foo():") == 1

    def test_callee_before_caller_in_output(self):
        callee = self._make_fn_doc("f1", "def callee():\n    return 0")
        caller = self._make_fn_doc("f2", "def caller():\n    return callee()")
        # callee comes first in post-order list
        docs = [callee, caller]
        result = WeaviateCodeDefinitionProcessor.restore_code_fragment(docs)
        assert result.index("def callee()") < result.index("def caller()")

    def test_empty_documents(self):
        result = WeaviateCodeDefinitionProcessor.restore_code_fragment([])
        assert result == ""

    def test_class_without_methods(self):
        class_doc = self._make_class_doc(
            "c1",
            "Solo",
            "class Solo:\n    def __init__(self):\n        pass",
        )
        result = WeaviateCodeDefinitionProcessor.restore_code_fragment([class_doc])
        assert "class Solo:" in result
        assert "def __init__" in result
