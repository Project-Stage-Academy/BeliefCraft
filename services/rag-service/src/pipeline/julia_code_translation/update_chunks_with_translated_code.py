"""Update translated algorithms/examples in chunks and enrich with usage metadata."""

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Literal, cast

from common.logging import get_logger
from pipeline.julia_code_translation.process_book_code import (
    BookCodeProcessor,
    JuliaEntityExtractor,
    TranslatedAlgorithmStore,
    UsageIndexBuilder,
)
from pipeline.julia_code_translation.translation_types import (
    Block,
    Chunk,
    TranslatedAlgorithm,
    TranslatedExample,
)
from pipeline.parsing.block_processor import open_block_processor

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


def prepare_blocks(
    book_pdf_path: str,
    ocr_dir: str,
    translated_algorithms_path: str | Path,
) -> list[Block]:
    """Extract algorithm/example blocks and populate usage metadata."""
    with open_block_processor(book_pdf_path, ocr_dir) as block_processor:
        blocks = block_processor.extract_algorithms_and_examples()

    book_processor = BookCodeProcessor(
        JuliaEntityExtractor(),
        UsageIndexBuilder(),
        TranslatedAlgorithmStore(Path(translated_algorithms_path)),
    )
    book_processor.extract_block_structs_and_functions(blocks)
    book_processor.extract_entities_usage(blocks)
    return cast(list[Block], blocks)


def find_used_entities(
    blocks: list[Block], entity_number: str, key: Literal["structs", "functions"]
) -> dict[str, list[str]]:
    """Return entities (structs or functions) referenced by algorithms that cite the entity number.

    The `key` argument should be either "structs" or "functions" (or any other mapping key present
    on algorithm blocks). Only inspects blocks labeled as "Algorithm".
    """
    if not entity_number:
        return {}

    used: defaultdict[str, list[str]] = defaultdict(list)
    for block in blocks:
        if block.get("block_type") == "Algorithm":
            for name, usages in block[key].items():
                if entity_number in usages:
                    entity_id = extract_entity_id_from_number(block.get("number", ""))
                    used[name].append(entity_id)
    return dict(used)


def format_translated_content(*parts: str) -> str:
    """Join translated content parts with a consistent double-newline separator."""
    return "\n\n".join(part for part in parts if part)


def update_algorithms(
    chunks: list[Chunk], translated_algorithms: list[TranslatedAlgorithm], blocks: list[Block]
) -> list[Chunk]:
    """Merge translated algorithm content and usage metadata into chunks."""
    for translated_item in translated_algorithms:
        entity_id = extract_entity_id_from_number(translated_item["algorithm_number"])
        found = False
        for chunk in chunks:
            if chunk.get("chunk_type") == "algorithm" and chunk.get("entity_id") == entity_id:
                chunk["content"] = format_translated_content(
                    translated_item["description"],
                    translated_item["code"],
                )
                chunk["declarations"] = list(translated_item["declarations"].values())
                chunk["used_structs"] = find_used_entities(
                    blocks, translated_item["algorithm_number"], "structs"
                )
                chunk["used_functions"] = find_used_entities(
                    blocks, translated_item["algorithm_number"], "functions"
                )
                found = True
                break
        if not found:
            logger.warning("Chunk for algorithm %s wasn't found!", entity_id)
    return chunks


def update_examples(
    chunks: list[Chunk], translated_examples: list[TranslatedExample], blocks: list[Block]
) -> list[Chunk]:
    """Merge translated example content and usage metadata into chunks."""
    for translated_item in translated_examples:
        entity_id = extract_entity_id_from_number(translated_item["example_number"])
        found = False
        for chunk in chunks:
            if chunk.get("chunk_type") == "example" and chunk.get("entity_id") == entity_id:
                chunk["content"] = format_translated_content(
                    translated_item["description"],
                    translated_item["text"],
                )
                chunk["used_structs"] = find_used_entities(
                    blocks, translated_item["example_number"], "structs"
                )
                chunk["used_functions"] = find_used_entities(
                    blocks, translated_item["example_number"], "functions"
                )
                found = True
                break
        if not found:
            logger.warning("Chunk for example %s wasn't found!", entity_id)
    return chunks


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for the update script."""
    parser = argparse.ArgumentParser(
        description="Update chunks with translated algorithms/examples and usage metadata."
    )
    parser.add_argument(
        "--pdf-path",
        dest="book_pdf",
        required=True,
        help="Path to the source book PDF.",
    )
    parser.add_argument(
        "--paddle-ocr-dir",
        dest="ocr_dir",
        required=True,
        help="OCR JSON directory name passed to the block processor.",
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

    blocks = prepare_blocks(args.book_pdf, args.ocr_dir, args.translated_algorithms)
    chunks = load_chunks(args.chunks)
    translated_algorithms = load_translated_algorithms(args.translated_algorithms)
    translated_examples = load_translated_examples(args.translated_examples)

    chunks = update_algorithms(chunks, translated_algorithms, blocks)
    chunks = update_examples(chunks, translated_examples, blocks)

    output_path = Path(args.output)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(chunks, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
