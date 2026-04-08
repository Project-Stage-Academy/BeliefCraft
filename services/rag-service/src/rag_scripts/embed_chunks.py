import argparse
import json
from pathlib import Path
from typing import Any

import weaviate
from rag_service.constants import COLLECTION_NAME, REFERENCE_TYPE_MAP
from weaviate.classes.config import Configure, ReferenceProperty
from weaviate.collections import Collection
from weaviate.collections.classes.config import VectorDistances
from weaviate.collections.classes.data import DataReference, DataReferenceMulti
from weaviate.util import generate_uuid5

PROPERTIES_TO_EMBED = ["content"]
EMBEDDING_MODEL_REGION = "us-east-1"
EMBEDDING_MODEL = "amazon.titan-embed-text-v2:0"


def setup_collection(client: weaviate.WeaviateClient, recreate: bool = False) -> Collection:
    """Initialize the unified collection schema with Bedrock embedding and cross-references."""
    if recreate and client.collections.exists(COLLECTION_NAME):
        print(f"Deleting existing collection: {COLLECTION_NAME}")
        client.collections.delete(COLLECTION_NAME)

    if not client.collections.exists(COLLECTION_NAME):
        print(f"Creating collection: {COLLECTION_NAME}")
        client.collections.create(
            name=COLLECTION_NAME,
            vector_config=Configure.Vectors.text2vec_aws_bedrock(
                source_properties=PROPERTIES_TO_EMBED,
                region=EMBEDDING_MODEL_REGION,
                model=EMBEDDING_MODEL,
                vector_index_config=Configure.VectorIndex.flat(
                    distance_metric=VectorDistances.COSINE,
                ),
            ),
            references=[
                ReferenceProperty(name=name, target_collection=COLLECTION_NAME)
                for name in REFERENCE_TYPE_MAP
            ],
        )
    else:
        print(f"Using existing collection: {COLLECTION_NAME}")
    return client.collections.use(COLLECTION_NAME)


def generate_deterministic_uuid(chunk: dict[str, Any]) -> str:
    """Generate a deterministic UUID based on entity_id and chunk_type
    if available, otherwise use whole chunk."""
    entity_id = chunk.get("entity_id", "")
    if entity_id:
        return generate_uuid5(f'{entity_id}:{chunk["chunk_type"]}')
    return generate_uuid5(repr(chunk))


ReferenceMap = dict[
    tuple[str, str], dict[str, Any]
]  # Mapping of (entity_id, chunk_type) to referencing chunks


def extract_references_from_chunk(
    chunk: dict[str, Any], reference_map: ReferenceMap
) -> list[DataReference | DataReferenceMulti]:
    """Extract references from chunks. Remove old reference fields from chunk because
    they will be passed separately to Weaviate

    Parameters
    ----------
    chunk: dict[str, Any]
        The chunk dictionary from which to extract references.
    reference_map: ReferenceMap
        A mapping of (entity_id, chunk_type) to the chunks that are referenced by this pair.
    """
    references: list[DataReference | DataReferenceMulti] = []
    from_id = generate_deterministic_uuid(chunk)
    for ref_name, chunk_type in REFERENCE_TYPE_MAP.items():
        chunk_references = chunk.pop(ref_name, [])
        if not chunk_references:
            continue
        for entity_id in chunk_references:
            key = (entity_id, chunk_type)
            try:
                referenced_chunk = reference_map[key]
            except KeyError:
                print(
                    f"Warning: Referenced chunk not found with entity_id={entity_id}, "
                    f"chunk_type={chunk_type}. Skipping reference."
                )
                continue
            to_id = generate_deterministic_uuid(referenced_chunk)
            references.append(
                DataReference(from_uuid=from_id, from_property=ref_name, to_uuid=to_id)
            )
    return references


def insert_chunks(
    collection: Collection, chunks: list[dict[str, Any]], reference_map: ReferenceMap
) -> None:
    """Iterate through chunks and insert them into Weaviate."""
    inserted_chunks_count = 0
    chunk_id_map: dict[str, dict[str, Any]] = {
        ch["chunk_id"]: ch for ch in chunks if "chunk_id" in ch
    }
    references: list[DataReference | DataReferenceMulti] = []
    seen_uuids: set[str] = set()
    with collection.batch.dynamic() as batch:
        for chunk in chunks:
            chunk_to_add = chunk.copy()
            if "defined_in_chunk" in chunk_to_add:
                parent_chunk_id = chunk_to_add["defined_in_chunk"]
                referenced_chunk = chunk_id_map.get(parent_chunk_id)
                if referenced_chunk is None:
                    print(
                        f"Warning: Chunk references unknown parent chunk_id='{parent_chunk_id}' "
                        f"via 'defined_in_chunk'. Skipping field."
                    )
                    chunk_to_add.pop("defined_in_chunk")
                else:
                    referenced_chunk_for_uuid = referenced_chunk.copy()
                    referenced_chunk_for_uuid.pop("chunk_id", "")
                    chunk_to_add["defined_in_chunk"] = generate_deterministic_uuid(
                        referenced_chunk_for_uuid
                    )
            uuid = generate_deterministic_uuid(chunk_to_add)
            if uuid in seen_uuids:
                print(
                    f"Warning: Duplicate UUID '{uuid}' detected. "
                    f"The previously inserted chunk with this UUID will be overwritten."
                )
            else:
                inserted_chunks_count += 1
            seen_uuids.add(uuid)
            chunk_references = extract_references_from_chunk(chunk_to_add, reference_map)
            batch.add_object(
                properties=chunk_to_add,
                uuid=uuid,
            )
            references.extend(chunk_references)
    # add references in batch after all chunks are inserted to avoid referencing non-existing UUIDs
    collection.data.reference_add_many(references)
    print(f"Inserted {inserted_chunks_count} chunks with {len(references)} references.")


def build_reference_map(chunks: list[dict[str, Any]]) -> ReferenceMap:
    """Build a mapping of (entity_id, chunk_type) to the chunks that are referenced by this pair."""
    reference_map = {}
    for chunk in chunks:
        if "entity_id" in chunk and "chunk_type" in chunk:
            key = (chunk["entity_id"], chunk["chunk_type"])
            reference_map[key] = chunk
    return reference_map


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Load and embed document chunks from JSON into Weaviate. Passes 'content' "
        "field to embedding model, sets up cross-references for fields: 'referenced_formulas', "
        "'referenced_algorithms', 'referenced_tables', 'referenced_figures', 'referenced_examples',"
        " 'referenced_exercises'. Ignores 'chunk_id' and generates own UUIDs. All other"
        " fields are treated as metadata and stored in Weaviate as is without embedding."
    )
    parser.add_argument("file_path", help="Path to the JSON file containing chunks.", type=Path)
    parser.add_argument(
        "--recreate", action="store_true", help="Delete and recreate the collection before loading."
    )
    args = parser.parse_args()

    try:
        with args.file_path.open(encoding="utf-8") as f:
            chunks = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Failed to load JSON file: {e}")
        return

    with weaviate.connect_to_local() as client:
        collection = setup_collection(client, recreate=args.recreate)
        reference_map = build_reference_map(chunks)
        insert_chunks(collection, chunks, reference_map)
        print(f"Successfully processed {len(chunks)} chunks.")


if __name__ == "__main__":
    main()
