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


class Chunk(TypedDict, total=False):
    type: str
    entity_id: str
    content: str
    caption: str
    declarations: list[str]
    used_algorithms: dict[str, str]


def load_translated_algorithms(filename: str | Path) -> list[TranslatedAlgorithm]:
    with Path(filename).open(encoding="utf-8") as f:
        data = json.load(f)
    return cast(list[TranslatedAlgorithm], data)


def load_translated_examples(filename: str | Path) -> list[dict[str, Any]]:
    with Path(filename).open(encoding="utf-8") as f:
        data = json.load(f)
    return cast(list[dict[str, Any]], data)


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


def find_used_algorithms(book_pdf_path: str, entity_number: str) -> list[str]:
    with open_block_processor(book_pdf_path) as block_processor:
        blocks = block_processor.extract_algorithms_and_examples()

        translated_algorithms_path = Path("translated_algorithms.json")
        book_processor = BookCodeProcessor(
            translated_algorithms_path,
            JuliaEntityExtractor(),
            UsageIndexBuilder(),
            TranslatedAlgorithmStore(translated_algorithms_path),
        )
        book_processor.extract_block_structs_and_functions(blocks)
        book_processor.extract_entities_usage(blocks)

        used_structs = defaultdict(list)
        for block in blocks:
            if block["type"] == "Algorithm":
                for struct_name, struct_usages in block["structs"].items():
                    if entity_number in struct_usages:
                        entity_id = extract_entity_id_from_number(block["number"])
                        used_structs[struct_name].append(entity_id)

                for struct_name, struct_usages in block["functions"].items():
                    if entity_number in struct_usages:
                        entity_id = extract_entity_id_from_number(block["number"])
                        used_structs[struct_name].append(entity_id)
        print()
    return []


def update_algorithms(
    chunks: list[Chunk], translated_algorithms: list[TranslatedAlgorithm]
) -> None:
    for translated_algorithm in translated_algorithms:
        entity_id = extract_entity_id_from_number(translated_algorithm["algorithm_number"])
        found = False
        for chunk in chunks:
            if chunk.get("type") == "algorithm" and chunk.get("entity_id") == entity_id:
                chunk["content"] = (
                    f"{translated_algorithm['code']}\n\n{translated_algorithm['description']}"
                )
                # chunk["caption"] = translated_algorithm["description"]
                chunk["declarations"] = list(translated_algorithm["declarations"].values())
                chunk["used_algorithms"] = {}
                found = True
                break
        if not found:
            raise ValueError(
                "Translated algorithm "
                f"{translated_algorithm['algorithm_number']} not found in chunks"
            )


find_used_algorithms("dm.pdf", "")
chunks = load_chunks("ULTIMATE_BOOK_DATA.json")
translated_algorithms = load_translated_algorithms("translated_algorithms.json")
translated_examples = load_translated_examples("translated_examples.json")

print(len(chunks))
