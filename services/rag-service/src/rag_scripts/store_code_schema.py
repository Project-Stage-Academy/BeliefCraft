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
CodeClass
  algorithm_ref         -> unified_collection  (the algorithm chunk that defines this class)

CodeMethod
  algorithm_ref         -> unified_collection  (the algorithm chunk that defines this method)
  class_ref             -> CodeClass           (the class this method belongs to)
  initialized_classes   -> CodeClass           (classes instantiated inside the method)
  referenced_methods    -> CodeMethod          (methods called inside the method)
  referenced_functions  -> CodeFunction        (functions called inside the method)

CodeFunction
  algorithm_ref         -> unified_collection  (the algorithm chunk that defines this function)
  initialized_classes   -> CodeClass
  referenced_methods    -> CodeMethod
  referenced_functions  -> CodeFunction

unified_collection (algorithm chunks)
  referenced_classes    -> CodeClass           (classes used in the algorithm)
  referenced_methods    -> CodeMethod          (methods used in the algorithm)
  referenced_functions  -> CodeFunction        (functions used in the algorithm)

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
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import weaviate
from common.logging import get_logger
from pipeline.code_processing.julia_code_translation.update_chunks_with_translated_code import (
    extract_entity_id_from_number,
)
from pipeline.code_processing.python_code_processing.build_code_schema import build_code_schema
from pipeline.code_processing.python_code_processing.extract_code_refs import (
    extract_code_refs,
)
from rag_service.constants import (
    ALGORITHM_REF_FIELD,
    CLASS_REF_FIELD,
    CODE_CLASS_COLLECTION,
    CODE_FUNCTION_COLLECTION,
    CODE_METHOD_COLLECTION,
    COLLECTION_NAME,
    ChunkCodeRef,
    CodeEntityRef,
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
        Property(name="content", data_type=DataType.TEXT, skip_vectorization=True),
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
    (CodeEntityRef.INITIALIZED_CLASSES.value, CODE_CLASS_COLLECTION),
    (CodeEntityRef.REFERENCED_METHODS.value, CODE_METHOD_COLLECTION),
    (CodeEntityRef.REFERENCED_FUNCTIONS.value, CODE_FUNCTION_COLLECTION),
]

# Back-reference from any code entity to the algorithm chunk that defines it.
_ALGORITHM_REF = (ALGORITHM_REF_FIELD, COLLECTION_NAME)


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
            ReferenceProperty(name=CLASS_REF_FIELD, target_collection=CODE_CLASS_COLLECTION),
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
    _add_missing_refs(cls_col, [_ALGORITHM_REF])
    _add_missing_refs(mth_col, _CROSS_REFS + [_ALGORITHM_REF])
    _add_missing_refs(fn_col, _CROSS_REFS + [_ALGORITHM_REF])

    return cls_col, mth_col, fn_col


# ---------------------------------------------------------------------------
# Reference builders
# ---------------------------------------------------------------------------


def _id_list_refs(from_uuid: str, prop: str, ids: list[str]) -> list[DataReference]:
    """Return one ``DataReference`` per schema id in *ids*, all pointing from *from_uuid*.*prop*."""
    return [
        DataReference(from_property=prop, from_uuid=from_uuid, to_uuid=uuid_for_schema_id(sid))
        for sid in ids
    ]


def _cross_refs(from_uuid: str, item: dict[str, Any]) -> RefList:
    """
    Build the three shared cross-references (initialized_classes, referenced_methods,
    referenced_functions).
    """
    refs: RefList = []
    refs.extend(
        _id_list_refs(
            from_uuid,
            CodeEntityRef.INITIALIZED_CLASSES.value,
            item.get(CodeEntityRef.INITIALIZED_CLASSES.value, []),
        )
    )
    refs.extend(
        _id_list_refs(
            from_uuid,
            CodeEntityRef.REFERENCED_METHODS.value,
            item.get(CodeEntityRef.REFERENCED_METHODS.value, []),
        )
    )
    refs.extend(
        _id_list_refs(
            from_uuid,
            CodeEntityRef.REFERENCED_FUNCTIONS.value,
            item.get(CodeEntityRef.REFERENCED_FUNCTIONS.value, []),
        )
    )
    return refs


def _algorithm_ref(from_uuid: str, entity: dict[str, Any]) -> RefList:
    """Return a single ``algorithm_ref`` DataReference for *entity*, or ``[]`` if not applicable."""
    algo_number = str(entity.get("algorithm_number", "")).strip()
    if not algo_number:
        return []
    return [
        DataReference(
            from_property="algorithm_ref",
            from_uuid=from_uuid,
            to_uuid=uuid_for_algorithm_chunk(algo_number),
        )
    ]


# ---------------------------------------------------------------------------
# Insertion helpers
# ---------------------------------------------------------------------------


def _insert_classes(collection: Collection, classes: list[dict[str, Any]]) -> RefList:
    """Batch-insert class objects and return their ``algorithm_ref`` references."""
    with collection.batch.dynamic() as batch:
        for cls in classes:
            batch.add_object(
                properties={
                    "schema_id": cls["id"],
                    "name": cls["name"],
                    "content": cls["code"],
                },
                uuid=uuid_for_schema_id(cls["id"]),
            )

    refs: RefList = []
    for cls in classes:
        from_uuid = uuid_for_schema_id(cls["id"])
        refs.extend(_algorithm_ref(from_uuid, cls))
    return refs


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
                "content": item["code"],
            }
            for key in extra_prop_keys or []:
                props[key] = item.get(key, "")
            batch.add_object(properties=props, uuid=uuid_for_schema_id(item["id"]))

    refs: RefList = []
    for item in items:
        from_uuid = uuid_for_schema_id(item["id"])
        refs.extend(_algorithm_ref(from_uuid, item))
        if extra_refs_fn:
            refs.extend(extra_refs_fn(from_uuid, item))
        refs.extend(_cross_refs(from_uuid, item))
    return refs


def _insert_methods(collection: Collection, methods: list[dict[str, Any]]) -> RefList:
    """Batch-insert method objects and return all their references."""

    def _class_ref(from_uuid: str, mth: dict[str, Any]) -> RefList:
        class_schema_id = mth.get("class", "")
        if class_schema_id and not class_schema_id.startswith("external:"):
            return [
                DataReference(
                    from_property=CLASS_REF_FIELD,
                    from_uuid=from_uuid,
                    to_uuid=uuid_for_schema_id(class_schema_id),
                )
            ]
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
# Chunk → code entity references (shared by algorithm and example chunks)
# ---------------------------------------------------------------------------

# Reference properties added to unified_collection chunks (both algorithm and example).
_CHUNK_CODE_REFS = [
    (ChunkCodeRef.REFERENCED_CLASSES.value, CODE_CLASS_COLLECTION),
    (ChunkCodeRef.REFERENCED_METHODS.value, CODE_METHOD_COLLECTION),
    (ChunkCodeRef.REFERENCED_FUNCTIONS.value, CODE_FUNCTION_COLLECTION),
]

# Maps extract_code_refs output keys to the Weaviate property names on the chunk.
_REFS_KEY_TO_PROP = {
    CodeEntityRef.INITIALIZED_CLASSES.value: ChunkCodeRef.REFERENCED_CLASSES.value,
    CodeEntityRef.REFERENCED_METHODS.value: ChunkCodeRef.REFERENCED_METHODS.value,
    CodeEntityRef.REFERENCED_FUNCTIONS.value: ChunkCodeRef.REFERENCED_FUNCTIONS.value,
}


def _ensure_chunk_code_ref_properties(client: weaviate.WeaviateClient) -> None:
    """Add the chunk → code reference properties to unified_collection if missing."""
    if not client.collections.exists(COLLECTION_NAME):
        logger.warning("%s not found; skipping chunk-code ref setup.", COLLECTION_NAME)
        return
    unified = client.collections.use(COLLECTION_NAME)
    _add_missing_refs(unified, _CHUNK_CODE_REFS)


def _build_chunk_code_references(
    chunks: list[dict[str, Any]],
    schema: dict[str, Any],
    *,
    number_key: str,
    text_key: str,
    uuid_fn: "Callable[[str], str]",
    chunk_label: str,
) -> RefList:
    """Extract code refs from each chunk and return the corresponding ``DataReference`` list.

    Args:
        chunks:      List of chunk dicts (algorithms or examples).
        schema:      Result of ``build_code_schema()``, used to resolve references.
        number_key:  Dict key that holds the chunk number (e.g. ``"algorithm_number"``).
        text_key:    Dict key that holds the Python text to scan (e.g. ``"code"`` or ``"text"``).
        uuid_fn:     Function mapping an entity id to the chunk's Weaviate UUID.
        chunk_label: Human-readable label used in warning messages (e.g. ``"algorithm"``).
    """
    references: RefList = []

    for chunk in chunks:
        number = chunk.get(number_key, "")
        entity_id = extract_entity_id_from_number(number)
        if not entity_id:
            logger.warning("Skipping %s with unparseable number: %r", chunk_label, number)
            continue

        refs = extract_code_refs(chunk.get(text_key, ""), schema)
        from_uuid = uuid_fn(entity_id)

        for ref_key, prop in _REFS_KEY_TO_PROP.items():
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
            f"Algorithm chunks in {COLLECTION_NAME} receive referenced_classes/methods/functions "
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
    algorithms: list[dict[str, Any]],
    schema: dict[str, Any],
    recreate: bool,
) -> None:
    """Store all code schema entities (classes, methods, functions) in Weaviate.

    Sets up the three code collections, inserts all objects, and adds
    cross-references between them. Each code entity receives an ``algorithm_ref``
    back-reference pointing to the algorithm chunk in ``unified_collection`` where
    it is defined. Also adds ``referenced_classes``, ``referenced_methods``, and
    ``referenced_functions`` references on algorithm chunks in ``unified_collection``
    by extracting code references from each algorithm's code.

    Args:
        client:     Active Weaviate client.
        algorithms: List of algorithm dicts with ``"algorithm_number"`` and ``"code"`` fields,
                    used to build algorithm → code entity references.
        schema:     Result of ``build_code_schema()`` with keys
                    ``"classes"``, ``"methods"``, ``"functions"``.
        recreate:   If True, drops and recreates the collections before inserting.
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
    _ensure_chunk_code_ref_properties(client)
    if client.collections.exists(COLLECTION_NAME):
        algo_refs = _build_chunk_code_references(
            algorithms,
            schema,
            number_key="algorithm_number",
            text_key="code",
            uuid_fn=uuid_for_algorithm_chunk,
            chunk_label="algorithm",
        )
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
    _ensure_chunk_code_ref_properties(client)

    if not client.collections.exists(COLLECTION_NAME):
        logger.warning(
            "Collection %s does not exist; skipping example → code entity references.",
            COLLECTION_NAME,
        )
        return
    example_refs = _build_chunk_code_references(
        examples,
        schema,
        number_key="example_number",
        text_key="text",
        uuid_fn=uuid_for_example_chunk,
        chunk_label="example",
    )
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
        store_schema(client, algorithms, schema, recreate=args.recreate)
        if examples:
            store_example_refs(client, examples, schema)

    logger.info(
        "Done. %d classes, %d methods, %d functions.", len(classes), len(methods), len(functions)
    )


if __name__ == "__main__":
    main()
