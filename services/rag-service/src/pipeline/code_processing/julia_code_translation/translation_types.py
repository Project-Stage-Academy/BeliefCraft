"""TypedDict definitions for translated code update pipeline."""

from typing import TypedDict


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
