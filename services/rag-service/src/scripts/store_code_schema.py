"""
store_code_schema.py
--------------------
Stores code schema (classes, methods, functions) produced by build_schema into Weaviate.

Three new collections are created alongside the existing unified_collection:
  - CodeClass    — Python class definitions
  - CodeMethod   — Python method definitions
  - CodeFunction — Python top-level function definitions

Cross-references
~~~~~~~~~~~~~~~~
CodeMethod
  class_ref             -> CodeClass           (the class this method belongs to)
  initialized_classes   -> CodeClass           (classes instantiated inside the method)
  referenced_methods    -> CodeMethod          (methods called inside the method)
  referenced_functions  -> CodeFunction        (functions called inside the method)

CodeFunction
  initialized_classes   -> CodeClass
  referenced_methods    -> CodeMethod
  referenced_functions  -> CodeFunction

unified_collection (algorithm chunks)
  defined_classes       -> CodeClass           (classes introduced in the algorithm)
  defined_methods       -> CodeMethod          (methods introduced in the algorithm)
  defined_functions     -> CodeFunction        (functions introduced in the algorithm)

unified_collection (example chunks)
  referenced_classes    -> CodeClass           (classes used in the example)
  referenced_methods    -> CodeMethod          (methods used in the example)
  referenced_functions  -> CodeFunction        (functions used in the example)

Usage
-----
    python store_code_schema.py <translated_algorithms.json> [--recreate]
"""

import argparse
import json
from pathlib import Path
from typing import Any, cast

import weaviate
from common.logging import get_logger
from pipeline.code_processing.julia_code_translation.update_chunks_with_translated_code import (
    extract_entity_id_from_number,
)
from pipeline.code_processing.python_code_processing.build_code_schema import build_code_schema
from pipeline.code_processing.python_code_processing.extract_example_refs import (
    extract_example_refs,
)
from rag_service.constants import (
    CODE_CLASS_COLLECTION,
    CODE_FUNCTION_COLLECTION,
    CODE_METHOD_COLLECTION,
    COLLECTION_NAME,
)
from weaviate.classes.config import Configure, DataType, Property, ReferenceProperty
from weaviate.classes.data import DataReference
from weaviate.collections import Collection
from weaviate.collections.classes.data import DataReferenceMulti
from weaviate.util import generate_uuid5

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

RefList = list[DataReference | DataReferenceMulti]

# ---------------------------------------------------------------------------
# UUID helpers
# ---------------------------------------------------------------------------


def uuid_for_schema_id(schema_id: str) -> str:
    """Deterministic UUID derived from a schema id string like ``'cls:Foo'`` or ``'fn:bar'``."""
    return generate_uuid5(schema_id)


def uuid_for_algorithm_chunk(entity_id: str) -> str:
    """
    Deterministic UUID for an algorithm chunk (``chunk_type='algorithm'``) in unified_collection.
    """
    return generate_uuid5(f"{entity_id}:algorithm")


def uuid_for_example_chunk(entity_id: str) -> str:
    """Deterministic UUID for an example chunk (``chunk_type='example'``) in unified_collection."""
    return generate_uuid5(f"{entity_id}:example")


# ---------------------------------------------------------------------------
# Collection setup
# ---------------------------------------------------------------------------


def _existing_reference_names(collection: Collection) -> set[str]:
    """Return the set of reference property names already configured on *collection*."""
    return {r.name for r in collection.config.get().references}


def _recreate_if_needed(client: weaviate.WeaviateClient, name: str, recreate: bool) -> None:
    """Delete collection *name* when *recreate* is True and it already exists."""
    if recreate and client.collections.exists(name):
        logger.info("Deleting existing collection: %s", name)
        client.collections.delete(name)


def _create_or_use(client: weaviate.WeaviateClient, name: str, **kwargs: Any) -> Collection:
    """Create collection *name* if absent, then return a handle to it."""
    if not client.collections.exists(name):
        logger.info("Creating collection: %s", name)
        client.collections.create(name=name, **kwargs)
    else:
        logger.info("Using existing collection: %s", name)
    return client.collections.use(name)


def _common_properties(extra: list[Property] | None = None) -> list[Property]:
    """Return the base property list shared by all three code collections, plus any *extra* ones."""
    base = [
        Property(name="schema_id", data_type=DataType.TEXT, skip_vectorization=True),
        Property(name="name", data_type=DataType.TEXT, skip_vectorization=True),
        Property(name="code", data_type=DataType.TEXT, skip_vectorization=True),
        Property(name="algorithm_number", data_type=DataType.TEXT, skip_vectorization=True),
    ]
    return base + (extra or [])


def _add_missing_refs(collection: Collection, refs: list[tuple[str, str]]) -> None:
    """Add reference properties to *collection* that are not yet configured."""
    existing = _existing_reference_names(collection)
    for ref_name, target in refs:
        if ref_name not in existing:
            collection.config.add_reference(
                ReferenceProperty(name=ref_name, target_collection=target)
            )


# Cross-collection references shared by both CodeMethod and CodeFunction.
_CROSS_REFS = [
    ("initialized_classes", CODE_CLASS_COLLECTION),
    ("referenced_methods", CODE_METHOD_COLLECTION),
    ("referenced_functions", CODE_FUNCTION_COLLECTION),
]


def setup_collections(
    client: weaviate.WeaviateClient, recreate: bool = False
) -> tuple[Collection, Collection, Collection]:
    """Create all three code collections and return ``(cls_col, mth_col, fn_col)``.

    Uses two phases to avoid circular-reference errors:
    - Phase 1: create each collection with only its non-circular references.
    - Phase 2: add cross-collection references once all collections exist.
    """
    for name in (CODE_CLASS_COLLECTION, CODE_METHOD_COLLECTION, CODE_FUNCTION_COLLECTION):
        _recreate_if_needed(client, name, recreate)

    no_vectorizer = Configure.Vectorizer.none()

    cls_col = _create_or_use(
        client,
        CODE_CLASS_COLLECTION,
        vectorizer_config=no_vectorizer,
        properties=_common_properties(),
        references=[],
    )
    mth_col = _create_or_use(
        client,
        CODE_METHOD_COLLECTION,
        vectorizer_config=no_vectorizer,
        properties=_common_properties(
            [Property(name="qualified_name", data_type=DataType.TEXT, skip_vectorization=True)]
        ),
        references=[
            ReferenceProperty(name="class_ref", target_collection=CODE_CLASS_COLLECTION),
        ],
    )
    fn_col = _create_or_use(
        client,
        CODE_FUNCTION_COLLECTION,
        vectorizer_config=no_vectorizer,
        properties=_common_properties(),
        references=[],
    )

    logger.info("Adding cross-collection references …")
    _add_missing_refs(mth_col, _CROSS_REFS)
    _add_missing_refs(fn_col, _CROSS_REFS)

    return cls_col, mth_col, fn_col


# ---------------------------------------------------------------------------
# Reference builders
# ---------------------------------------------------------------------------


def _id_list_refs(from_uuid: str, prop: str, ids: list[str]) -> list[DataReference]:
    """Return one ``DataReference`` per schema id in *ids*, all pointing from *from_uuid*.*prop*."""
    return [DataReference(from_uuid, prop, uuid_for_schema_id(sid)) for sid in ids]


def _cross_refs(from_uuid: str, item: dict[str, Any]) -> RefList:
    """
    Build the three shared cross-references (initialized_classes, referenced_methods,
    referenced_functions).
    """
    refs: RefList = []
    refs.extend(
        _id_list_refs(from_uuid, "initialized_classes", item.get("initialized_classes", []))
    )
    refs.extend(_id_list_refs(from_uuid, "referenced_methods", item.get("referenced_methods", [])))
    refs.extend(
        _id_list_refs(from_uuid, "referenced_functions", item.get("referenced_functions", []))
    )
    return refs


# ---------------------------------------------------------------------------
# Insertion helpers
# ---------------------------------------------------------------------------


def _insert_classes(collection: Collection, classes: list[dict[str, Any]]) -> RefList:
    """Batch-insert class objects. No algorithm-level back-references are stored here."""
    with collection.batch.dynamic() as batch:
        for cls in classes:
            batch.add_object(
                properties={
                    "schema_id": cls["id"],
                    "name": cls["name"],
                    "code": cls["code"],
                    "algorithm_number": str(cls.get("algorithm_number", "")),
                },
                uuid=uuid_for_schema_id(cls["id"]),
            )
    return []


def _insert_code_entities(
    collection: Collection,
    items: list[dict[str, Any]],
    extra_prop_keys: list[str] | None = None,
    extra_refs_fn: Any = None,
) -> RefList:
    """Batch-insert method or function objects and return all their references.

    Args:
        collection:     Target Weaviate collection.
        items:          List of schema records to insert.
        extra_prop_keys: Additional property keys to copy from each item
                         (e.g. ``["qualified_name"]``).
        extra_refs_fn:  Optional ``(from_uuid, item) -> RefList`` called per item for extra refs.
    """
    with collection.batch.dynamic() as batch:
        for item in items:
            props: dict[str, Any] = {
                "schema_id": item["id"],
                "name": item["name"],
                "code": item["code"],
                "algorithm_number": str(item.get("algorithm_number", "")),
            }
            for key in extra_prop_keys or []:
                props[key] = item.get(key, "")
            batch.add_object(properties=props, uuid=uuid_for_schema_id(item["id"]))

    refs: RefList = []
    for item in items:
        from_uuid = uuid_for_schema_id(item["id"])
        if extra_refs_fn:
            refs.extend(extra_refs_fn(from_uuid, item))
        refs.extend(_cross_refs(from_uuid, item))
    return refs


def _insert_methods(collection: Collection, methods: list[dict[str, Any]]) -> RefList:
    """Batch-insert method objects and return all their references."""

    def _class_ref(from_uuid: str, mth: dict[str, Any]) -> RefList:
        class_schema_id = mth.get("class", "")
        if class_schema_id and not class_schema_id.startswith("external:"):
            return [DataReference(from_uuid, "class_ref", uuid_for_schema_id(class_schema_id))]
        return []

    return _insert_code_entities(
        collection,
        methods,
        extra_prop_keys=["qualified_name"],
        extra_refs_fn=_class_ref,
    )


def _insert_functions(collection: Collection, functions: list[dict[str, Any]]) -> RefList:
    """Batch-insert function objects and return all their references."""
    return _insert_code_entities(collection, functions)


def _add_references_safely(collection: Collection, references: RefList, label: str) -> None:
    """Call ``reference_add_many`` and log a warning instead of raising on failure."""
    if not references:
        return
    try:
        collection.data.reference_add_many(references)
        logger.info("Added %d references for %s.", len(references), label)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Some references for %s could not be added: %s", label, exc)


# ---------------------------------------------------------------------------
# Algorithm → code entity references (defined_classes/methods/functions)
# ---------------------------------------------------------------------------

_ALGORITHM_CODE_REFS = [
    ("defined_classes", CODE_CLASS_COLLECTION),
    ("defined_methods", CODE_METHOD_COLLECTION),
    ("defined_functions", CODE_FUNCTION_COLLECTION),
]


def _ensure_algorithm_code_ref_properties(client: weaviate.WeaviateClient) -> None:
    """Add the algorithm → code reference properties to unified_collection if missing."""
    if not client.collections.exists(COLLECTION_NAME):
        logger.warning("%s not found; skipping algorithm-code ref setup.", COLLECTION_NAME)
        return
    unified = client.collections.use(COLLECTION_NAME)
    _add_missing_refs(unified, _ALGORITHM_CODE_REFS)


def _build_algorithm_code_references(
    schema: dict[str, Any],
) -> RefList:
    """
    Build ``defined_classes``, ``defined_methods``, and ``defined_functions`` references from
    each code entity back to the algorithm chunk that introduced it.
    """
    references: RefList = []

    for cls in schema.get("classes", []):
        algo_number = str(cls.get("algorithm_number", "")).strip()
        if not algo_number:
            continue
        from_uuid = uuid_for_algorithm_chunk(algo_number)
        references.extend(_id_list_refs(from_uuid, "defined_classes", [cls["id"]]))

    for mth in schema.get("methods", []):
        algo_number = str(mth.get("algorithm_number", "")).strip()
        if not algo_number:
            continue
        from_uuid = uuid_for_algorithm_chunk(algo_number)
        references.extend(_id_list_refs(from_uuid, "defined_methods", [mth["id"]]))

    for fn in schema.get("functions", []):
        algo_number = str(fn.get("algorithm_number", "")).strip()
        if not algo_number:
            continue
        from_uuid = uuid_for_algorithm_chunk(algo_number)
        references.extend(_id_list_refs(from_uuid, "defined_functions", [fn["id"]]))

    return references


# ---------------------------------------------------------------------------
# Example → code entity references
# ---------------------------------------------------------------------------

_EXAMPLE_CODE_REFS = [
    ("referenced_classes", CODE_CLASS_COLLECTION),
    ("referenced_methods", CODE_METHOD_COLLECTION),
    ("referenced_functions", CODE_FUNCTION_COLLECTION),
]

_EXAMPLE_REFS_KEY_TO_PROP = {
    "initialized_classes": "referenced_classes",
    "referenced_methods": "referenced_methods",
    "referenced_functions": "referenced_functions",
}


def _ensure_example_code_ref_properties(client: weaviate.WeaviateClient) -> None:
    """Add the example → code reference properties to unified_collection if missing."""
    if not client.collections.exists(COLLECTION_NAME):
        logger.warning("%s not found; skipping example-code ref setup.", COLLECTION_NAME)
        return
    unified = client.collections.use(COLLECTION_NAME)
    _add_missing_refs(unified, _EXAMPLE_CODE_REFS)


def _build_example_code_references(
    examples: list[dict[str, Any]],
    schema: dict[str, Any],
) -> RefList:
    """
    Extract code refs from each example's text and return the corresponding ``DataReference`` list.
    """
    references: RefList = []

    for example in examples:
        example_number = example.get("example_number", "")
        entity_id = extract_entity_id_from_number(example_number)
        if not entity_id:
            logger.warning("Skipping example with unparseable number: %r", example_number)
            continue

        refs = extract_example_refs(example.get("text", ""), schema)
        from_uuid = uuid_for_example_chunk(entity_id)

        for ref_key, prop in _EXAMPLE_REFS_KEY_TO_PROP.items():
            references.extend(_id_list_refs(from_uuid, prop, refs.get(ref_key, [])))

    return references


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build and store code schema (classes, methods, functions) from translated "
            "algorithms JSON into Weaviate. Creates three collections: "
            f"{CODE_CLASS_COLLECTION}, {CODE_METHOD_COLLECTION}, {CODE_FUNCTION_COLLECTION}. "
            "Each entity stores its code, metadata, and cross-references to related code entities. "
            f"Algorithm chunks in {COLLECTION_NAME} receive defined_classes/methods/functions "
            "references, and example chunks receive referenced_classes/methods/functions links."
        )
    )
    parser.add_argument(
        "--algorithms_file_path",
        default="translated_algorithms.json",
        help="Path to the translated_algorithms.json file.",
        type=Path,
    )
    parser.add_argument(
        "--examples_file_path",
        default="translated_examples.json",
        help="Path to the translated_examples.json file.",
        type=Path,
    )
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="Delete and recreate the code collections before loading.",
    )
    return parser


def _load_json(path: Path, label: str) -> list[dict[str, Any]] | None:
    """Load and return a JSON file as a list, or log an error and return ``None``."""
    try:
        with path.open() as f:
            return cast(list[dict[str, Any]], json.load(f))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        logger.error("Failed to load %s JSON: %s", label, exc)
        return None


def store_schema(
    client: weaviate.WeaviateClient,
    schema: dict[str, Any],
    recreate: bool,
) -> None:
    """Store all code schema entities (classes, methods, functions) in Weaviate.

    Sets up the three code collections, inserts all objects, and adds
    cross-references between them. Also adds ``defined_classes``,
    ``defined_methods``, and ``defined_functions`` references on algorithm chunks
    in ``unified_collection``.

    Args:
        client:   Active Weaviate client.
        schema:   Result of ``build_code_schema()`` with keys
                  ``"classes"``, ``"methods"``, ``"functions"``.
        recreate: If True, drops and recreates the collections before inserting.
    """
    classes, methods, functions = schema["classes"], schema["methods"], schema["functions"]
    cls_col, mth_col, fn_col = setup_collections(client, recreate=recreate)

    logger.info("Inserting classes …")
    _add_references_safely(cls_col, _insert_classes(cls_col, classes), CODE_CLASS_COLLECTION)

    logger.info("Inserting methods …")
    _add_references_safely(mth_col, _insert_methods(mth_col, methods), CODE_METHOD_COLLECTION)

    logger.info("Inserting functions …")
    _add_references_safely(fn_col, _insert_functions(fn_col, functions), CODE_FUNCTION_COLLECTION)

    logger.info("Adding algorithm → code entity references …")
    _ensure_algorithm_code_ref_properties(client)
    if client.collections.exists(COLLECTION_NAME):
        algo_refs = _build_algorithm_code_references(schema)
        unified_col = client.collections.use(COLLECTION_NAME)
        _add_references_safely(unified_col, algo_refs, f"{COLLECTION_NAME} (algorithms)")


def store_example_refs(
    client: weaviate.WeaviateClient,
    examples: list[dict[str, Any]],
    schema: dict[str, Any],
) -> None:
    """Add references from example chunks in unified_collection to code entities.

    For each example, extracts code references from its text and creates
    cross-reference links to the relevant CodeClass, CodeMethod, and CodeFunction objects.

    Args:
        client:   Active Weaviate client.
        examples: List of example dicts, each with ``"example_number"`` and ``"text"`` fields.
        schema:   Result of ``build_code_schema()``, used to resolve named references.
    """
    logger.info("Adding example → code entity references …")
    _ensure_example_code_ref_properties(client)

    if not client.collections.exists(COLLECTION_NAME):
        logger.warning(
            "Collection %s does not exist; skipping example → code entity references.",
            COLLECTION_NAME,
        )
        return
    example_refs = _build_example_code_references(examples, schema)
    unified_col = client.collections.use(COLLECTION_NAME)
    _add_references_safely(unified_col, example_refs, f"{COLLECTION_NAME} (examples)")
    logger.info("Processed %d examples.", len(examples))


def main() -> None:
    args = _build_arg_parser().parse_args()

    algorithms = _load_json(args.algorithms_file_path, "algorithms")
    if algorithms is None:
        return

    examples: list[dict[str, Any]] = []
    if args.examples_file_path is not None:
        loaded = _load_json(args.examples_file_path, "examples")
        if loaded is None:
            return
        examples = loaded
        logger.info("Loaded %d examples from %s", len(examples), args.examples_file_path)

    logger.info("Building code schema …")
    schema = build_code_schema(algorithms)
    classes, methods, functions = schema["classes"], schema["methods"], schema["functions"]
    logger.info(
        "Classes: %d  Methods: %d  Functions: %d", len(classes), len(methods), len(functions)
    )

    with weaviate.connect_to_local() as client:
        store_schema(client, schema, recreate=args.recreate)
        if examples:
            store_example_refs(client, examples, schema)

    logger.info(
        "Done. %d classes, %d methods, %d functions.", len(classes), len(methods), len(functions)
    )


if __name__ == "__main__":
    main()
