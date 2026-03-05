"""
embed_code_schema.py
--------------------
Embeds code schema (classes, methods, functions) produced by build_schema into Weaviate.

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
    python embed_code_schema.py <translated_algorithms.json> [--recreate]
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import weaviate
from weaviate.classes.config import Configure, DataType, Property, ReferenceProperty
from weaviate.classes.data import DataReference
from weaviate.collections import Collection
from weaviate.util import generate_uuid5

# Ensure the pipeline package is importable when running from repo root
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.julia_code_translation.build_schema import build_schema
from rag_service.constants import (
    CODE_CLASS_COLLECTION,
    CODE_FUNCTION_COLLECTION,
    CODE_METHOD_COLLECTION,
    COLLECTION_NAME,
)

# ---------------------------------------------------------------------------
# UUID helpers
# ---------------------------------------------------------------------------


def uuid_for_schema_id(schema_id: str) -> str:
    """Deterministic UUID derived from a schema id string like 'cls:Foo' or 'fn:bar'."""
    return generate_uuid5(schema_id)


def uuid_for_algorithm_chunk(entity_id: str) -> str:
    """Deterministic UUID for an algorithm chunk in unified_collection.

    embed_chunks.py generates UUIDs via:
        generate_uuid5(f'{entity_id}:{chunk_type}')
    for chunks that have an entity_id. Algorithm chunks have chunk_type='algorithm'.
    """
    return generate_uuid5(f"{entity_id}:algorithm")


# ---------------------------------------------------------------------------
# Collection setup
# ---------------------------------------------------------------------------


def _recreate_if_needed(client: weaviate.WeaviateClient, name: str, recreate: bool) -> None:
    if recreate and client.collections.exists(name):
        print(f"Deleting existing collection: {name}")
        client.collections.delete(name)


def _existing_reference_names(collection: Collection) -> set[str]:
    """Return the set of reference property names already on a collection."""
    cfg = collection.config.get()
    return {r.name for r in cfg.references}


def setup_collections(
    client: weaviate.WeaviateClient, recreate: bool = False
) -> tuple[Collection, Collection, Collection]:
    """Create all three code collections.

    Done in two phases to avoid circular-reference errors:
      Phase 1 — create each collection with only its non-circular references
                 (algorithm_ref, class_ref).
      Phase 2 — add the cross-collection references (initialized_classes,
                 used_methods, used_functions) once all collections exist.
    """
    for name in (CODE_CLASS_COLLECTION, CODE_METHOD_COLLECTION, CODE_FUNCTION_COLLECTION):
        _recreate_if_needed(client, name, recreate)

    # ------------------------------------------------------------------
    # Phase 1: create collections (no cross-collection refs yet)
    # ------------------------------------------------------------------
    if not client.collections.exists(CODE_CLASS_COLLECTION):
        print(f"Creating collection: {CODE_CLASS_COLLECTION}")
        client.collections.create(
            name=CODE_CLASS_COLLECTION,
            vectorizer_config=Configure.Vectorizer.none(),
            properties=[
                Property(name="schema_id", data_type=DataType.TEXT, skip_vectorization=True),
                Property(name="name", data_type=DataType.TEXT, skip_vectorization=True),
                Property(name="code", data_type=DataType.TEXT, skip_vectorization=True),
                Property(name="algorithm_number", data_type=DataType.TEXT, skip_vectorization=True),
            ],
            references=[
                ReferenceProperty(name="algorithm_ref", target_collection=COLLECTION_NAME),
            ],
        )
    else:
        print(f"Using existing collection: {CODE_CLASS_COLLECTION}")

    if not client.collections.exists(CODE_METHOD_COLLECTION):
        print(f"Creating collection: {CODE_METHOD_COLLECTION}")
        client.collections.create(
            name=CODE_METHOD_COLLECTION,
            vectorizer_config=Configure.Vectorizer.none(),
            properties=[
                Property(name="schema_id", data_type=DataType.TEXT, skip_vectorization=True),
                Property(name="name", data_type=DataType.TEXT, skip_vectorization=True),
                Property(name="qualified_name", data_type=DataType.TEXT, skip_vectorization=True),
                Property(name="code", data_type=DataType.TEXT, skip_vectorization=True),
                Property(name="algorithm_number", data_type=DataType.TEXT, skip_vectorization=True),
            ],
            references=[
                ReferenceProperty(name="algorithm_ref", target_collection=COLLECTION_NAME),
                ReferenceProperty(name="class_ref", target_collection=CODE_CLASS_COLLECTION),
            ],
        )
    else:
        print(f"Using existing collection: {CODE_METHOD_COLLECTION}")

    if not client.collections.exists(CODE_FUNCTION_COLLECTION):
        print(f"Creating collection: {CODE_FUNCTION_COLLECTION}")
        client.collections.create(
            name=CODE_FUNCTION_COLLECTION,
            vectorizer_config=Configure.Vectorizer.none(),
            properties=[
                Property(name="schema_id", data_type=DataType.TEXT, skip_vectorization=True),
                Property(name="name", data_type=DataType.TEXT, skip_vectorization=True),
                Property(name="code", data_type=DataType.TEXT, skip_vectorization=True),
                Property(name="algorithm_number", data_type=DataType.TEXT, skip_vectorization=True),
            ],
            references=[
                ReferenceProperty(name="algorithm_ref", target_collection=COLLECTION_NAME),
            ],
        )
    else:
        print(f"Using existing collection: {CODE_FUNCTION_COLLECTION}")

    cls_col = client.collections.use(CODE_CLASS_COLLECTION)
    mth_col = client.collections.use(CODE_METHOD_COLLECTION)
    fn_col = client.collections.use(CODE_FUNCTION_COLLECTION)

    # ------------------------------------------------------------------
    # Phase 2: add cross-collection references now that all three exist
    # ------------------------------------------------------------------
    print("Adding cross-collection references …")

    existing_mth_refs = _existing_reference_names(mth_col)
    for ref_name, target in (
        ("initialized_classes", CODE_CLASS_COLLECTION),
        ("used_methods", CODE_METHOD_COLLECTION),
        ("used_functions", CODE_FUNCTION_COLLECTION),
    ):
        if ref_name not in existing_mth_refs:
            mth_col.config.add_reference(ReferenceProperty(name=ref_name, target_collection=target))

    existing_fn_refs = _existing_reference_names(fn_col)
    for ref_name, target in (
        ("initialized_classes", CODE_CLASS_COLLECTION),
        ("used_methods", CODE_METHOD_COLLECTION),
        ("used_functions", CODE_FUNCTION_COLLECTION),
    ):
        if ref_name not in existing_fn_refs:
            fn_col.config.add_reference(ReferenceProperty(name=ref_name, target_collection=target))

    return cls_col, mth_col, fn_col


# ---------------------------------------------------------------------------
# Insertion helpers
# ---------------------------------------------------------------------------


def _insert_classes(
    collection: Collection,
    classes: list[dict[str, Any]],
) -> list[DataReference]:
    """Insert class objects and return algorithm_ref references to add later."""
    references: list[DataReference] = []

    with collection.batch.dynamic() as batch:
        for cls in classes:
            uuid = uuid_for_schema_id(cls["id"])
            batch.add_object(
                properties={
                    "schema_id": cls["id"],
                    "name": cls["name"],
                    "code": cls["code"],
                    "algorithm_number": str(cls.get("algorithm_number", "")),
                },
                uuid=uuid,
            )

    # Build algorithm_ref references after objects exist
    for cls in classes:
        algo_number = str(cls.get("algorithm_number", "")).strip()
        if algo_number:
            from_uuid = uuid_for_schema_id(cls["id"])
            to_uuid = uuid_for_algorithm_chunk(algo_number)
            references.append(
                DataReference(
                    from_uuid=from_uuid,
                    from_property="algorithm_ref",
                    to_uuid=to_uuid,
                )
            )

    return references


def _insert_methods(
    collection: Collection,
    methods: list[dict[str, Any]],
) -> list[DataReference]:
    """Insert method objects and return all cross-references to add later."""
    references: list[DataReference] = []

    with collection.batch.dynamic() as batch:
        for mth in methods:
            uuid = uuid_for_schema_id(mth["id"])
            batch.add_object(
                properties={
                    "schema_id": mth["id"],
                    "name": mth["name"],
                    "qualified_name": mth["qualified_name"],
                    "code": mth["code"],
                    "algorithm_number": str(mth.get("algorithm_number", "")),
                },
                uuid=uuid,
            )

    # Build all references
    for mth in methods:
        from_uuid = uuid_for_schema_id(mth["id"])

        # algorithm_ref
        algo_number = str(mth.get("algorithm_number", "")).strip()
        if algo_number:
            references.append(
                DataReference(
                    from_uuid=from_uuid,
                    from_property="algorithm_ref",
                    to_uuid=uuid_for_algorithm_chunk(algo_number),
                )
            )

        # class_ref (belongs-to class)
        class_schema_id = mth.get("class", "")
        if class_schema_id and not class_schema_id.startswith("external:"):
            references.append(
                DataReference(
                    from_uuid=from_uuid,
                    from_property="class_ref",
                    to_uuid=uuid_for_schema_id(class_schema_id),
                )
            )

        # initialized_classes
        for cls_id in mth.get("initialized_classes", []):
            references.append(
                DataReference(
                    from_uuid=from_uuid,
                    from_property="initialized_classes",
                    to_uuid=uuid_for_schema_id(cls_id),
                )
            )

        # used_methods
        for mth_id in mth.get("used_methods", []):
            references.append(
                DataReference(
                    from_uuid=from_uuid,
                    from_property="used_methods",
                    to_uuid=uuid_for_schema_id(mth_id),
                )
            )

        # used_functions
        for fn_id in mth.get("used_functions", []):
            references.append(
                DataReference(
                    from_uuid=from_uuid,
                    from_property="used_functions",
                    to_uuid=uuid_for_schema_id(fn_id),
                )
            )

    return references


def _insert_functions(
    collection: Collection,
    functions: list[dict[str, Any]],
) -> list[DataReference]:
    """Insert function objects and return all cross-references to add later."""
    references: list[DataReference] = []

    with collection.batch.dynamic() as batch:
        for fn in functions:
            uuid = uuid_for_schema_id(fn["id"])
            batch.add_object(
                properties={
                    "schema_id": fn["id"],
                    "name": fn["name"],
                    "code": fn["code"],
                    "algorithm_number": str(fn.get("algorithm_number", "")),
                },
                uuid=uuid,
            )

    # Build all references
    for fn in functions:
        from_uuid = uuid_for_schema_id(fn["id"])

        # algorithm_ref
        algo_number = str(fn.get("algorithm_number", "")).strip()
        if algo_number:
            references.append(
                DataReference(
                    from_uuid=from_uuid,
                    from_property="algorithm_ref",
                    to_uuid=uuid_for_algorithm_chunk(algo_number),
                )
            )

        # initialized_classes
        for cls_id in fn.get("initialized_classes", []):
            references.append(
                DataReference(
                    from_uuid=from_uuid,
                    from_property="initialized_classes",
                    to_uuid=uuid_for_schema_id(cls_id),
                )
            )

        # used_methods
        for mth_id in fn.get("used_methods", []):
            references.append(
                DataReference(
                    from_uuid=from_uuid,
                    from_property="used_methods",
                    to_uuid=uuid_for_schema_id(mth_id),
                )
            )

        # used_functions
        for fn_id in fn.get("used_functions", []):
            references.append(
                DataReference(
                    from_uuid=from_uuid,
                    from_property="used_functions",
                    to_uuid=uuid_for_schema_id(fn_id),
                )
            )

    return references


def _add_references_safely(
    collection: Collection, references: list[DataReference], label: str
) -> None:
    """Add references in batch, skipping failures gracefully."""
    if not references:
        return
    try:
        collection.data.reference_add_many(list(references))
        print(f"  Added {len(references)} references for {label}.")
    except Exception as exc:  # noqa: BLE001
        print(f"  Warning: some references for {label} could not be added: {exc}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Build and embed code schema (classes, methods, functions) from translated "
            "algorithms JSON into Weaviate. Creates three collections: "
            f"{CODE_CLASS_COLLECTION}, {CODE_METHOD_COLLECTION}, {CODE_FUNCTION_COLLECTION}. "
            "Each entity stores its code (embedded via Bedrock), metadata, and cross-references "
            "to related code entities and to the originating algorithm chunk in the "
            f"{COLLECTION_NAME} collection."
        )
    )
    parser.add_argument(  # TODO: make it positional
        "--file_path",
        default="translated_algorithms.json",
        help="Path to the translated_algorithms.json file.",
        type=Path,
    )
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="Delete and recreate the code collections before loading.",
    )
    args = parser.parse_args()

    try:
        with args.file_path.open() as f:
            algorithms = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"Failed to load JSON file: {exc}")
        return

    print("Building code schema from translated algorithms …")
    schema = build_schema(algorithms)

    classes = schema["classes"]
    methods = schema["methods"]
    functions = schema["functions"]

    print(f"  Classes:   {len(classes)}")
    print(f"  Methods:   {len(methods)}")
    print(f"  Functions: {len(functions)}")

    with weaviate.connect_to_local() as client:
        cls_col, mth_col, fn_col = setup_collections(client, recreate=args.recreate)

        print("Inserting classes …")
        cls_refs = _insert_classes(cls_col, classes)
        _add_references_safely(cls_col, cls_refs, CODE_CLASS_COLLECTION)

        print("Inserting methods …")
        mth_refs = _insert_methods(mth_col, methods)
        # Split references by target collection so we call reference_add_many on the right
        # collection object (Weaviate v4 client resolves the from_property automatically,
        # but we still call it on the collection that owns the from-object).
        _add_references_safely(mth_col, mth_refs, CODE_METHOD_COLLECTION)

        print("Inserting functions …")
        fn_refs = _insert_functions(fn_col, functions)
        _add_references_safely(fn_col, fn_refs, CODE_FUNCTION_COLLECTION)

    print("Done.")
    print(
        f"  Processed {len(classes)} classes, {len(methods)} methods, {len(functions)} functions."
    )


if __name__ == "__main__":
    main()
