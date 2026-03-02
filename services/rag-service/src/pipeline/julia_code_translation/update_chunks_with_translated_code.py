import json
from pathlib import Path
from typing import Any, TypedDict, cast


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


def update_algorithms(
    chunks: list[Chunk], translated_algorithms: list[TranslatedAlgorithm]
) -> None:
    for translated_algorithm in translated_algorithms:
        entity_id = extract_entity_id_from_number(translated_algorithm["algorithm_number"])
        found = False
        for chunk in chunks:
            if chunk.get("type") == "algorithm" and chunk.get("entity_id") == entity_id:
                chunk["content"] = translated_algorithm["code"]
                chunk["caption"] = translated_algorithm["description"]
                chunk["declarations"] = list(translated_algorithm["declarations"].values())
                found = True
                break
        if not found:
            raise ValueError(
                "Translated algorithm "
                f"{translated_algorithm['algorithm_number']} not found in chunks"
            )


chunks = load_chunks("ULTIMATE_BOOK_DATA.json")
translated_algorithms = load_translated_algorithms("translated_algorithms.json")
translated_examples = load_translated_examples("translated_examples.json")

print(len(chunks))
