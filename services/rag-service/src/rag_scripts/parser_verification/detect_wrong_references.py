# pragma: no cover
import argparse
import json
from pathlib import Path
from typing import Any

from rag_service.constants import REFERENCE_TYPE_MAP


def build_reference_map(chunks: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    """Build a mapping of (entity_id, chunk_type) to the chunks that are referenced by this pair."""
    reference_map = {}
    for chunk in chunks:
        if "entity_id" in chunk and "chunk_type" in chunk:
            key = (chunk["entity_id"], chunk["chunk_type"])
            reference_map[key] = chunk
    return reference_map


def detect_wrong_references(
    chunks: list[dict[str, Any]], reference_map: dict[tuple[str, str], dict[str, Any]]
) -> list[dict[str, Any]]:
    """Identify references to entity_ids that do not exist in the reference_map."""
    wrong_references = []
    for chunk in chunks:
        source_info = {
            "chunk_id": chunk.get("chunk_id"),
            "entity_id": chunk.get("entity_id"),
            "chunk_type": chunk.get("chunk_type"),
        }

        for ref_name, expected_chunk_type in REFERENCE_TYPE_MAP.items():
            # Use get() instead of pop() to avoid modifying the original chunk data
            chunk_references = chunk.get(ref_name, [])
            if not chunk_references:
                continue

            for entity_id in chunk_references:
                key = (entity_id, expected_chunk_type)
                if key not in reference_map:
                    wrong_references.append(
                        {
                            "source_chunk": source_info,
                            "reference_field": ref_name,
                            "missing_entity_id": entity_id,
                            "expected_chunk_type": expected_chunk_type,
                        }
                    )
    return wrong_references


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Detect wrong references in document chunks JSON file."
    )
    parser.add_argument("file_path", help="Path to the JSON file containing chunks.", type=Path)
    parser.add_argument(
        "--output",
        help="Path to the output JSON file. Defaults to wrong_references.json",
        type=Path,
        default=Path("wrong_references.json"),
    )
    args = parser.parse_args()

    try:
        with args.file_path.open() as f:
            chunks = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Failed to load JSON file: {e}")
        return

    reference_map = build_reference_map(chunks)
    wrong_refs = detect_wrong_references(chunks, reference_map)

    if wrong_refs:
        print(f"Found {len(wrong_refs)} wrong references. Writing to {args.output}")
        with args.output.open("w") as f:
            json.dump(wrong_refs, f, indent=2)
    else:
        print("No wrong references found.")


if __name__ == "__main__":
    main()
