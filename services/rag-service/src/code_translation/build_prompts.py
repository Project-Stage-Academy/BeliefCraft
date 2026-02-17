import json
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Optional

from code_translation.prompts import update_descriptions_prompt, translate_python_code_prompt, translate_example_prompt
from code_translation.python_github_code import get_translated_python_code_from_github
from pdf_parsing.extract_algorithms_and_examples import extract_algorithms_and_examples, extract_algorithms, BlockType
import re

APPENDIX_START_CHAPTER = 28
APPENDIX_LETTERS = set("ABCDEFGH")
PROMPTS_DIR = Path("prompts")


def extract_entities_from_julia_code(code: str):
    """Return top-level structs and function names defined in a Julia code block."""
    IDENT = r"[A-Za-z_\u0080-\uFFFF]\w*"
    FUNC_NAME = rf"{IDENT}[!?]?"

    oneliner_func_re = re.compile(rf"^\s*({FUNC_NAME})\s*\([^=\n]*\)\s*=")
    block_func_re = re.compile(rf"^\s*function\s+({FUNC_NAME})\(")
    struct_re = re.compile(rf"^\s*(?:mutable\s+)?struct\s+({IDENT})\b")

    block_open_re = re.compile(
        r"^\s*(function|(?:mutable\s+)?struct|if|for|while|begin|let|try|quote|macro|module)\b"
    )

    block_end_re = re.compile(r"(?<!:)\bend\b")

    STOPWORDS = {
        "if", "for", "while", "begin", "let",
        "try", "catch", "finally", "end", "do"
    }

    structs, functions = [], []
    seen_structs, seen_funcs = set(), set()

    depth = 0

    for raw in code.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue

        opens = 1 if block_open_re.match(line) else 0

        ends = len(block_end_re.findall(line))

        # Only capture top-level declarations to avoid nested helpers.
        if depth == 0:
            m = struct_re.match(line)
            if m:
                name = m.group(1)
                if name not in seen_structs:
                    seen_structs.add(name)
                    structs.append(name)

            m = block_func_re.match(line)
            if m:
                name = m.group(1)
                if name not in STOPWORDS and name not in seen_funcs:
                    seen_funcs.add(name)
                    functions.append(name)

            m = oneliner_func_re.match(line)
            if m:
                name = m.group(1)
                if name not in STOPWORDS and name not in seen_funcs:
                    seen_funcs.add(name)
                    functions.append(name)

        depth = max(0, depth + opens - ends)

    return structs, functions


def extract_block_number_from_caption(caption: str) -> str:
    """Normalize a caption into its stable key, e.g. 'Algorithm 2.1.'"""
    parts = caption.split()
    if len(parts) < 2:
        return caption
    return f"{parts[0]} {parts[1]}"


def extract_chapter_from_block_caption(caption: str) -> str:
    """Extract the chapter component from a block caption string."""
    block_number = caption.split(" ")[1]
    return block_number.split(".")[0]


def get_blocks_with_chapter(blocks, chapter_number: str):
    """Filter blocks to those belonging to a given chapter number."""
    chapter_blocks = []

    for block in blocks:
        if extract_chapter_from_block_caption(block["caption"]) == chapter_number:
            chapter_blocks.append(block)
    return chapter_blocks


def find_related_definitions(block_number, blocks):
    """Find (entity, block_number) pairs that reference the given block."""
    related = []
    for block in blocks:
        if block["number"] == block_number:
            continue

        for item, used_list in block["functions"].items():
            if block_number in used_list:
                related.append((item, block["number"]))

        for item, used_list in block["structs"].items():
            if block_number in used_list:
                related.append((item, block["number"]))
    return related


def find_related_definitions_for_chapter(chapter_blocks, all_blocks):
    """Build a per-block map of related definitions for a chapter."""
    related = {}
    for block in chapter_blocks:
        block_number = block["number"]
        related[block_number] = find_related_definitions(block_number, all_blocks)
    return related


def extract_block_structs_and_functions(blocks) -> None:
    """Annotate blocks with declared structs/functions and their usage lists."""
    for block in blocks:
        block["number"] = extract_block_number_from_caption(block["caption"])
        structs, functions = extract_entities_from_julia_code(block["text"])
        block["structs"] = {struct: [] for struct in structs}
        block["functions"] = {func: [] for func in functions}


def extract_entities_usage(blocks, blocks_type: BlockType = BlockType.ALGORITHM) -> None:
    """Populate per-block usage lists for structs/functions across blocks."""
    for block in blocks:
        if block["block_type"] != blocks_type.value:
            continue

        for struct_name, used_list in block["structs"].items():
            for second_block in blocks:
                if second_block is block:
                    continue
                struct_as_typing = f"::{struct_name}"
                called_structure = f"{struct_name}("
                if struct_as_typing in second_block["text"] or called_structure in second_block["text"]:
                    used_list.append(second_block["number"])

        for function_name, used_list in block["functions"].items():
            for second_block in blocks:
                if second_block is block:
                    continue
                function_as_definition = f"function {function_name}("
                function_as_short_definition_pattern = rf"\b{re.escape(function_name)}\s*\([^)]*\)\s*="
                if (
                    f"{function_name}(" in second_block["text"]
                    and not (
                        function_as_definition in second_block["text"]
                        or re.search(function_as_short_definition_pattern, second_block["text"])
                    )
                ):
                    used_list.append(second_block["number"])



@lru_cache(maxsize=1)
def _load_translated_algorithms() -> list:
    """Load translated algorithms JSON once per run."""
    json_path = Path("translated_algorithms.json")
    with json_path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def get_translated_algorithm(algorithm_number: str) -> Optional[str]:
    """Return translated code for a given algorithm number."""
    json_data = _load_translated_algorithms()

    for item in json_data:
        if item["algorithm_number"] == algorithm_number:
            return item["code"]
    return None


def _normalize_chapter(chapter) -> int:
    """Convert a chapter identifier to a numeric value (A-H mapped after 28)."""
    chapter_str = str(chapter)
    if chapter_str in APPENDIX_LETTERS:
        return APPENDIX_START_CHAPTER + ord(chapter_str) - ord("A")
    return int(chapter_str)


def extract_block_chapter(block_number: str) -> int:
    """Extract and normalize chapter number from a block key."""
    number = block_number.split(" ")[1]
    chapter = number.split(".")[0]
    return _normalize_chapter(chapter)


def get_translated_algorithms(algorithm_numbers: Iterable[str]):
    """Hydrate a list of algorithm numbers with translated code entries."""
    return [
        {
            "algorithm_number": algorithm_number,
            "translated": get_translated_algorithm(algorithm_number)
        } for algorithm_number in algorithm_numbers
    ]


def filter_out_older_chapters(block_numbers, current_chapter):
    """Filter block numbers to those at or before the given chapter."""
    current_chapter = _normalize_chapter(current_chapter)
    filtered = []
    for block_number in block_numbers:
        chapter = extract_block_chapter(block_number)
        if chapter <= current_chapter:
            filtered.append(block_number)
    return filtered


def _format_blocks_text(blocks) -> str:
    """Render blocks as prompt-ready caption + code text."""
    return "\n".join(f"{block['caption']} \n\n {block['text']} \n\n" for block in blocks)


def _format_translated_blocks(translated_blocks) -> str:
    """Render translated algorithms as prompt-ready text."""
    return "\n".join(
        f"{translated['algorithm_number']} \n\n {translated['translated']} \n\n"
        for translated in translated_blocks
    )


def build_update_descriptions_prompt(chapter, julia_code):
    """Build a prompt to update algorithm descriptions for a chapter."""
    julia_chapter_code = get_blocks_with_chapter(julia_code, str(int(chapter)))
    extract_block_structs_and_functions(julia_chapter_code)
    python_chapter_code = get_translated_python_code_from_github(chapter, None)

    return update_descriptions_prompt.format(
        _format_blocks_text(julia_chapter_code),
        python_chapter_code,
    )


def build_translate_python_code_prompt(chapter, julia_code):
    """Build a prompt to translate Julia algorithms in a chapter to Python."""
    extract_block_structs_and_functions(julia_code)
    extract_entities_usage(julia_code)

    try:
        chapter_number = str(int(chapter))
    except ValueError:
        chapter_number = chapter

    julia_chapter_code = get_blocks_with_chapter(julia_code, chapter_number)
    related_entities = find_related_definitions_for_chapter(julia_chapter_code, julia_code)

    related_algorithms = set()
    for entities in related_entities.values():
        for entity in entities:
            related_algorithms.add(entity[1])
    filtered_related_algorithms = filter_out_older_chapters(related_algorithms, chapter)
    translated_algorithms = get_translated_algorithms(filtered_related_algorithms)

    return translate_python_code_prompt.format(
        _format_blocks_text(julia_chapter_code),
        _format_translated_blocks(translated_algorithms),
    )


def build_translate_example_prompt(example_number, blocks):
    """Build a prompt to translate a single example block to Python."""
    extract_block_structs_and_functions(blocks)
    extract_entities_usage(blocks)

    example = None
    for block in blocks:
        if block["number"] == example_number:
            example = block
            break

    if not example:
        raise ValueError(f"Example with number {example_number} not found")

    related_entities = find_related_definitions(example_number, blocks)
    related_algorithms = set()
    for entity in related_entities:
        related_algorithms.add(entity[1])

    filtered_related_algorithms = filter_out_older_chapters(
        related_algorithms,
        extract_block_chapter(example_number),
    )
    translated_examples = get_translated_algorithms(filtered_related_algorithms)

    return translate_example_prompt.format(
        f"{example['caption']} \n\n {example['text']} \n\n",
        "\n".join(f"{translated['translated']} \n\n" for translated in translated_examples),
    )


if __name__ == "__main__":
    example_with_code_numbers = [
        "Example 2.3.",
        "Example 2.5.",
        "Example 4.1.",
        "Example 4.2.",
        "Example 9.10.",
        "Example 10.1.",
        "Example 11.2.",
        "Example 15.2.",
        "Example 17.2.",
        "Example 17.3.",
        "Example 17.4.",
        "Example 21.1.",
        "Example 22.1.",
        "Example 22.3.",
        "Example 22.6.",
    ]

    translated_chapters = [
        "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12", "14", "15", "16", "17", "20", "24",
    ]

    chapters_to_translate = ["13", "18", "19", "21", "22", "23", "25", "26", "27", "E"]

    blocks = extract_algorithms_and_examples("dm.pdf")

    julia_code = extract_algorithms(blocks)

    for chapter in translated_chapters:
        prompt = build_update_descriptions_prompt(chapter, julia_code)
        PROMPTS_DIR.mkdir(parents=True, exist_ok=True)
        with open(f"prompts/chapter_{chapter}_code_translation.txt", "w", encoding="utf-8") as f:
            f.write(prompt)

    for chapter in chapters_to_translate:
        prompt = build_translate_python_code_prompt(chapter, julia_code)
        with open(f"prompts/chapter_{chapter}_translation.txt", "w", encoding="utf-8") as f:
            f.write(prompt)

    for example in example_with_code_numbers:
        prompt = build_translate_example_prompt(example, blocks)
        with open(f"prompts/{example.replace(' ', '_')}_translation.txt", "w", encoding="utf-8") as f:
            f.write(prompt)
