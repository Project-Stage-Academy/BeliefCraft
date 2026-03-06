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
  algorithm_ref  -> unified_collection  (chunk_type="algorithm", entity_id=algorithm_number)

CodeMethod
  algorithm_ref        -> unified_collection  (algorithm chunk)
  class_ref            -> CodeClass           (the class this method belongs to)
  initialized_classes  -> CodeClass           (classes instantiated inside the method)
  used_methods         -> CodeMethod          (methods called inside the method)
  used_functions       -> CodeFunction        (functions called inside the method)

CodeFunction
  algorithm_ref        -> unified_collection  (algorithm chunk)
  initialized_classes  -> CodeClass
  used_methods         -> CodeMethod
  used_functions       -> CodeFunction

Usage
-----
    python store_code_schema.py <translated_algorithms.json> [--recreate]
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, cast

import weaviate
from common.logging import get_logger
from pipeline.code_processing.julia_code_translation.update_chunks_with_translated_code import (
    extract_entity_id_from_number,
)
from pipeline.code_processing.python_code_processing.build_code_schema import build_code_schema
from weaviate.classes.config import Configure, DataType, Property, ReferenceProperty
from weaviate.classes.data import DataReference
from weaviate.collections import Collection
from weaviate.collections.classes.data import DataReferenceMulti
from weaviate.util import generate_uuid5

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.code_processing.python_code_processing.extract_example_refs import (
    extract_example_refs,
)
from rag_service.constants import (
    CODE_CLASS_COLLECTION,
    CODE_FUNCTION_COLLECTION,
    CODE_METHOD_COLLECTION,
    COLLECTION_NAME,
)

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

RefList = list[DataReference | DataReferenceMulti]

# ---------------------------------------------------------------------------
# UUID helpers
# ---------------------------------------------------------------------------


def uuid_for_schema_id(schema_id: str) -> str:
    """Deterministic UUID derived from a schema id string like 'cls:Foo' or 'fn:bar'."""
    return generate_uuid5(schema_id)


def uuid_for_algorithm_chunk(entity_id: str) -> str:
    """Deterministic UUID for an algorithm chunk (chunk_type='algorithm') in unified_collection."""
    return generate_uuid5(f"{entity_id}:algorithm")


def uuid_for_example_chunk(entity_id: str) -> str:
    """Deterministic UUID for an example chunk (chunk_type='example') in unified_collection."""
    return generate_uuid5(f"{entity_id}:example")


# ---------------------------------------------------------------------------
# Collection setup
# ---------------------------------------------------------------------------


def _existing_reference_names(collection: Collection) -> set[str]:
    return {r.name for r in collection.config.get().references}


def _recreate_if_needed(client: weaviate.WeaviateClient, name: str, recreate: bool) -> None:
    if recreate and client.collections.exists(name):
        logger.info("Deleting existing collection: %s", name)
        client.collections.delete(name)


def _create_or_use(client: weaviate.WeaviateClient, name: str, **kwargs: Any) -> Collection:
    if not client.collections.exists(name):
        logger.info("Creating collection: %s", name)
        client.collections.create(name=name, **kwargs)
    else:
        logger.info("Using existing collection: %s", name)
    return client.collections.use(name)


def _common_properties(extra: list[Property] | None = None) -> list[Property]:
    base = [
        Property(name="schema_id", data_type=DataType.TEXT, skip_vectorization=True),
        Property(name="name", data_type=DataType.TEXT, skip_vectorization=True),
        Property(name="code", data_type=DataType.TEXT, skip_vectorization=True),
        Property(name="algorithm_number", data_type=DataType.TEXT, skip_vectorization=True),
    ]
    return base + (extra or [])


def _add_missing_refs(collection: Collection, refs: list[tuple[str, str]]) -> None:
    existing = _existing_reference_names(collection)
    for ref_name, target in refs:
        if ref_name not in existing:
            collection.config.add_reference(
                ReferenceProperty(name=ref_name, target_collection=target)
            )


_CROSS_REFS = [
    ("initialized_classes", CODE_CLASS_COLLECTION),
    ("used_methods", CODE_METHOD_COLLECTION),
    ("used_functions", CODE_FUNCTION_COLLECTION),
]


def setup_collections(
    client: weaviate.WeaviateClient, recreate: bool = False
) -> tuple[Collection, Collection, Collection]:
    """
    Create all three code collections in two phases to avoid circular-reference errors:
      Phase 1 — create each collection with only its non-circular references.
      Phase 2 — add cross-collection references once all collections exist.
    """
    for name in (CODE_CLASS_COLLECTION, CODE_METHOD_COLLECTION, CODE_FUNCTION_COLLECTION):
        _recreate_if_needed(client, name, recreate)

    no_vectorizer = Configure.Vectorizer.none()

    cls_col = _create_or_use(
        client,
        CODE_CLASS_COLLECTION,
        vectorizer_config=no_vectorizer,
        properties=_common_properties(),
        references=[ReferenceProperty(name="algorithm_ref", target_collection=COLLECTION_NAME)],
    )
    mth_col = _create_or_use(
        client,
        CODE_METHOD_COLLECTION,
        vectorizer_config=no_vectorizer,
        properties=_common_properties(
            [
                Property(name="qualified_name", data_type=DataType.TEXT, skip_vectorization=True),
            ]
        ),
        references=[
            ReferenceProperty(name="algorithm_ref", target_collection=COLLECTION_NAME),
            ReferenceProperty(name="class_ref", target_collection=CODE_CLASS_COLLECTION),
        ],
    )
    fn_col = _create_or_use(
        client,
        CODE_FUNCTION_COLLECTION,
        vectorizer_config=no_vectorizer,
        properties=_common_properties(),
        references=[ReferenceProperty(name="algorithm_ref", target_collection=COLLECTION_NAME)],
    )

    logger.info("Adding cross-collection references …")
    _add_missing_refs(mth_col, _CROSS_REFS)
    _add_missing_refs(fn_col, _CROSS_REFS)

    return cls_col, mth_col, fn_col


def _make_ref(from_uuid: str, prop: str, to_uuid: str) -> DataReference:
    return DataReference(from_uuid=from_uuid, from_property=prop, to_uuid=to_uuid)


def _algorithm_ref(from_uuid: str, item: dict[str, Any]) -> DataReference | None:
    algo_number = str(item.get("algorithm_number", "")).strip()
    if algo_number:
        return _make_ref(from_uuid, "algorithm_ref", uuid_for_algorithm_chunk(algo_number))
    return None


def _id_list_refs(from_uuid: str, prop: str, ids: list[str]) -> list[DataReference]:
    return [_make_ref(from_uuid, prop, uuid_for_schema_id(sid)) for sid in ids]


def _cross_refs(from_uuid: str, item: dict[str, Any]) -> RefList:
    refs: RefList = []
    refs.extend(
        _id_list_refs(from_uuid, "initialized_classes", item.get("initialized_classes", []))
    )
    refs.extend(_id_list_refs(from_uuid, "used_methods", item.get("used_methods", [])))
    refs.extend(_id_list_refs(from_uuid, "used_functions", item.get("used_functions", [])))
    return refs


def _insert_classes(collection: Collection, classes: list[dict[str, Any]]) -> RefList:
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

    refs: RefList = []
    for cls in classes:
        ref = _algorithm_ref(uuid_for_schema_id(cls["id"]), cls)
        if ref:
            refs.append(ref)
    return refs


def _insert_code_entities(
    collection: Collection,
    items: list[dict[str, Any]],
    extra_props: dict[str, Any] | None = None,
    extra_refs_fn: Any = None,
) -> RefList:
    """Generic inserter for methods and functions."""
    with collection.batch.dynamic() as batch:
        for item in items:
            props = {
                "schema_id": item["id"],
                "name": item["name"],
                "code": item["code"],
                "algorithm_number": str(item.get("algorithm_number", "")),
            }
            if extra_props:
                for key in extra_props:
                    props[key] = item.get(key, "")
            batch.add_object(properties=props, uuid=uuid_for_schema_id(item["id"]))

    refs: RefList = []
    for item in items:
        from_uuid = uuid_for_schema_id(item["id"])
        ref = _algorithm_ref(from_uuid, item)
        if ref:
            refs.append(ref)
        if extra_refs_fn:
            refs.extend(extra_refs_fn(from_uuid, item))
        refs.extend(_cross_refs(from_uuid, item))
    return refs


def _insert_methods(collection: Collection, methods: list[dict[str, Any]]) -> RefList:
    def _class_ref(from_uuid: str, mth: dict[str, Any]) -> RefList:
        class_schema_id = mth.get("class", "")
        if class_schema_id and not class_schema_id.startswith("external:"):
            return [_make_ref(from_uuid, "class_ref", uuid_for_schema_id(class_schema_id))]
        return []

    return _insert_code_entities(
        collection,
        methods,
        extra_props={"qualified_name": None},
        extra_refs_fn=_class_ref,
    )


def _insert_functions(collection: Collection, functions: list[dict[str, Any]]) -> RefList:
    return _insert_code_entities(collection, functions)


def _add_references_safely(collection: Collection, references: RefList, label: str) -> None:
    if not references:
        return
    try:
        collection.data.reference_add_many(references)
        logger.info("Added %d references for %s.", len(references), label)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Some references for %s could not be added: %s", label, exc)


_EXAMPLE_CODE_REFS = [
    ("used_classes", CODE_CLASS_COLLECTION),
    ("used_methods", CODE_METHOD_COLLECTION),
    ("used_functions", CODE_FUNCTION_COLLECTION),
]

_EXAMPLE_REFS_KEY_TO_PROP = {
    "initialized_classes": "used_classes",
    "used_methods": "used_methods",
    "used_functions": "used_functions",
}


def _ensure_example_code_ref_properties(client: weaviate.WeaviateClient) -> None:
    if not client.collections.exists(COLLECTION_NAME):
        logger.warning("%s not found; skipping example-code ref setup.", COLLECTION_NAME)
        return
    unified = client.collections.use(COLLECTION_NAME)
    _add_missing_refs(unified, _EXAMPLE_CODE_REFS)


def _build_example_code_references(
    examples: list[dict[str, Any]],
    schema: dict[str, Any],
) -> RefList:
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


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build and store code schema (classes, methods, functions) from translated "
            "algorithms JSON into Weaviate. Creates three collections: "
            f"{CODE_CLASS_COLLECTION}, {CODE_METHOD_COLLECTION}, {CODE_FUNCTION_COLLECTION}. "
            "Each entity stores its code, metadata, and cross-references to related code entities "
            f"and to the originating algorithm chunk in {COLLECTION_NAME}."
        )
    )
    parser.add_argument(
        "--file_path",
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
    try:
        with path.open() as f:
            return cast(list[dict[str, Any]], json.load(f))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        logger.error("Failed to load %s JSON: %s", label, exc)
        return None


def _store_schema(
    client: weaviate.WeaviateClient,
    schema: dict[str, Any],
    recreate: bool,
) -> None:
    classes, methods, functions = schema["classes"], schema["methods"], schema["functions"]
    cls_col, mth_col, fn_col = setup_collections(client, recreate=recreate)

    logger.info("Inserting classes …")
    _add_references_safely(cls_col, _insert_classes(cls_col, classes), CODE_CLASS_COLLECTION)

    logger.info("Inserting methods …")
    _add_references_safely(mth_col, _insert_methods(mth_col, methods), CODE_METHOD_COLLECTION)

    logger.info("Inserting functions …")
    _add_references_safely(fn_col, _insert_functions(fn_col, functions), CODE_FUNCTION_COLLECTION)


def _store_example_refs(
    client: weaviate.WeaviateClient,
    examples: list[dict[str, Any]],
    schema: dict[str, Any],
) -> None:
    logger.info("Adding example → code entity references …")
    _ensure_example_code_ref_properties(client)
    example_refs = _build_example_code_references(examples, schema)
    unified_col = client.collections.use(COLLECTION_NAME)
    _add_references_safely(unified_col, example_refs, f"{COLLECTION_NAME} (examples)")
    logger.info("Processed %d examples.", len(examples))


def main() -> None:
    args = _build_arg_parser().parse_args()

    algorithms = _load_json(args.file_path, "algorithms")
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
        _store_schema(client, schema, recreate=args.recreate)
        if examples:
            _store_example_refs(client, examples, schema)

    logger.info(
        "Done. %d classes, %d methods, %d functions.", len(classes), len(methods), len(functions)
    )


if __name__ == "__main__":
    main()
