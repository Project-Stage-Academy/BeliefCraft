import json
from collections import defaultdict
from pathlib import Path
from typing import Any, TypedDict, cast

from pipeline.julia_code_translation.process_book_code import (
    BookCodeProcessor,
    JuliaEntityExtractor,
    TranslatedAlgorithmStore,
    UsageIndexBuilder,
)
from pipeline.parsing.block_processor import open_block_processor


class TranslatedAlgorithm(TypedDict):
    algorithm_number: str
    code: str
    description: str
    declarations: dict[str, str]


class TranslatedExample(TypedDict):
    example_number: str
    description: str
    text: str


class Chunk(TypedDict, total=False):
    chunk_type: str
    entity_id: str
    content: str
    caption: str
    declarations: list[str]
    used_algorithms: dict[str, str]
    used_structs: dict[str, list[str]]
    used_functions: dict[str, list[str]]


class Block(TypedDict):
    block_type: str
    number: str
    caption: str
    text: str
    structs: dict[str, list[str]]
    functions: dict[str, list[str]]


def load_translated_algorithms(filename: str | Path) -> list[TranslatedAlgorithm]:
    with Path(filename).open(encoding="utf-8") as f:
        data = json.load(f)
    return cast(list[TranslatedAlgorithm], data)


def load_translated_examples(filename: str | Path) -> list[TranslatedExample]:
    with Path(filename).open(encoding="utf-8") as f:
        data = json.load(f)
    return cast(list[TranslatedExample], data)


def load_chunks(filename: str | Path) -> list[Chunk]:
    with Path(filename).open(encoding="utf-8") as f:
        data = json.load(f)
    return cast(list[Chunk], data)


def extract_entity_id_from_number(number: str) -> str:
    # Example input: "Algorithm 1.1."
    # We want to extract "1.1"
    parts = number.split()
    if len(parts) < 2:
        return ""
    return parts[1].rstrip(".")


def prepare_blocks(book_pdf_path: str) -> list[Block]:
    with open_block_processor(book_pdf_path, "ocr_jsons") as block_processor:
        blocks = cast(list[Block], block_processor.extract_algorithms_and_examples())

    book_processor = BookCodeProcessor(
        JuliaEntityExtractor(),
        UsageIndexBuilder(),
        TranslatedAlgorithmStore(Path("translated_algorithms.json")),
    )
    blocks_any = cast(list[dict[str, Any]], cast(object, blocks))
    book_processor.extract_block_structs_and_functions(blocks_any)
    book_processor.extract_entities_usage(blocks_any)
    return blocks


def find_used_algorithms(
    blocks: list[Block], entity_number: str
) -> tuple[dict[str, list[str]], dict[str, list[str]]]:

    used_structs: defaultdict[str, list[str]] = defaultdict(list)
    used_function: defaultdict[str, list[str]] = defaultdict(list)
    for block in blocks:
        if block["block_type"] == "Algorithm":
            for struct_name, struct_usages in block["structs"].items():
                if entity_number in struct_usages:
                    entity_id = extract_entity_id_from_number(block["number"])
                    used_structs[struct_name].append(entity_id)

            for struct_name, struct_usages in block["functions"].items():
                if entity_number in struct_usages:
                    entity_id = extract_entity_id_from_number(block["number"])
                    used_function[struct_name].append(entity_id)
    return dict(used_structs), dict(used_function)


def update_algorithms(
    chunks: list[Chunk], translated_algorithms: list[TranslatedAlgorithm], blocks: list[Block]
) -> list[Chunk]:
    for translated_algorithm in translated_algorithms:
        entity_id = extract_entity_id_from_number(translated_algorithm["algorithm_number"])
        for chunk in chunks:
            if chunk.get("chunk_type") == "algorithm" and chunk.get("entity_id") == entity_id:
                chunk["content"] = (
                    f"{translated_algorithm['description']}\n\n{translated_algorithm['code']}"
                )
                chunk["declarations"] = list(translated_algorithm["declarations"].values())
                chunk["used_structs"], chunk["used_functions"] = find_used_algorithms(
                    blocks, translated_algorithm["algorithm_number"]
                )
                break
    return chunks


def update_examples_algorithms(
    chunks: list[Chunk], translated_examples: list[TranslatedExample], blocks: list[Block]
) -> list[Chunk]:
    for translated_example in translated_examples:
        entity_id = extract_entity_id_from_number(translated_example["example_number"])
        for chunk in chunks:
            if chunk.get("chunk_type") == "example" and chunk.get("entity_id") == entity_id:
                chunk["content"] = (
                    f"{translated_example['description']}\n\n{translated_example['text']}"
                )
                chunk["used_structs"], chunk["used_functions"] = find_used_algorithms(
                    blocks, translated_example["example_number"]
                )
                break
    return chunks


blocks = prepare_blocks("dm.pdf")
chunks = load_chunks("ULTIMATE_BOOK_DATA.json")
translated_algorithms = load_translated_algorithms("translated_algorithms.json")
translated_examples = load_translated_examples("translated_examples.json")

chunks = update_algorithms(chunks, translated_algorithms, blocks)
chunks = update_examples_algorithms(chunks, translated_examples, blocks)

output_path = Path("ULTIMATE_BOOK_DATA_translated.json")
with output_path.open("w", encoding="utf-8") as f:
    json.dump(chunks, f, ensure_ascii=False, indent=2)
