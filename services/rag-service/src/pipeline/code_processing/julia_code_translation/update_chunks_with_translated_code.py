"""Update translated algorithms/examples in chunks and enrich with usage metadata."""

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import cast

from common.logging import get_logger
from pipeline.code_processing.julia_code_translation.translation_types import (
    Chunk,
    TranslatedAlgorithm,
    TranslatedExample,
)

logger = get_logger(__name__)


def load_translated_algorithms(filename: str | Path) -> list[TranslatedAlgorithm]:
    """Load translated algorithms JSON from disk."""
    with Path(filename).open(encoding="utf-8") as f:
        data = json.load(f)
    return cast(list[TranslatedAlgorithm], data)


def load_translated_examples(filename: str | Path) -> list[TranslatedExample]:
    """Load translated examples JSON from disk."""
    with Path(filename).open(encoding="utf-8") as f:
        data = json.load(f)
    return cast(list[TranslatedExample], data)


def load_chunks(filename: str | Path) -> list[Chunk]:
    """Load chunk records JSON from disk."""
    with Path(filename).open(encoding="utf-8") as f:
        data = json.load(f)
    return cast(list[Chunk], data)


def extract_entity_id_from_number(number: str) -> str:
    """Extract the entity id from a numbered label like 'Algorithm 1.1.'

    Example input: "Algorithm 1.1." -> "1.1"
    """
    parts = number.split()
    if len(parts) < 2:
        return ""
    return parts[1].rstrip(".")


def format_translated_content(*parts: str) -> str:
    """Join translated content parts with a consistent double-newline separator."""
    return "\n\n".join(part for part in parts if part)


def _is_algorithm(item: TranslatedAlgorithm | TranslatedExample) -> bool:
    """Check whether the translated item is an algorithm."""
    return "algorithm_number" in item


def _update_chunks(
    chunks: list[Chunk],
    translated_items: Sequence[TranslatedAlgorithm | TranslatedExample],
) -> list[Chunk]:
    """
    Merge translated items into chunks in-place, updating content, declarations, and usage metadata.
    """
    for item in translated_items:
        if _is_algorithm(item):
            algo = cast(TranslatedAlgorithm, item)
            chunk_type = "algorithm"
            entity_number = algo["algorithm_number"]
            content = format_translated_content(algo["description"], algo["code"])
        else:
            example = cast(TranslatedExample, item)
            chunk_type = "example"
            entity_number = example["example_number"]
            content = format_translated_content(example["description"], example["text"])

        entity_id = extract_entity_id_from_number(entity_number)

        found = False
        for chunk in chunks:
            if chunk.get("chunk_type") == chunk_type and chunk.get("entity_id") == entity_id:
                chunk["content"] = content
                found = True
                break

        if not found:
            logger.warning("Chunk for %s %s wasn't found!", chunk_type, entity_id)

    return chunks


def update_algorithms(
    chunks: list[Chunk], translated_algorithms: list[TranslatedAlgorithm]
) -> list[Chunk]:
    """Merge translated algorithm content and usage metadata into chunks."""
    return _update_chunks(chunks, translated_algorithms)


def update_examples(
    chunks: list[Chunk], translated_examples: list[TranslatedExample]
) -> list[Chunk]:
    """Merge translated example content and usage metadata into chunks."""
    return _update_chunks(chunks, translated_examples)


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for the update script."""
    parser = argparse.ArgumentParser(
        description="Update chunks with translated algorithms/examples and usage metadata."
    )
    parser.add_argument(
        "--chunks",
        required=True,
        help="Path to the input chunks JSON.",
    )
    parser.add_argument(
        "--translated-algorithms",
        required=True,
        help="Path to translated algorithms JSON.",
    )
    parser.add_argument(
        "--translated-examples",
        required=True,
        help="Path to translated examples JSON.",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Path to the output JSON file.",
    )
    return parser.parse_args()


def main() -> None:
    """CLI entry point."""
    args = parse_args()

    chunks = load_chunks(args.chunks)
    translated_algorithms = load_translated_algorithms(args.translated_algorithms)
    translated_examples = load_translated_examples(args.translated_examples)

    chunks = update_algorithms(chunks, translated_algorithms)
    chunks = update_examples(chunks, translated_examples)

    output_path = Path(args.output)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(chunks, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
