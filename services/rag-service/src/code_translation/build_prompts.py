import argparse
from pathlib import Path

from code_translation.github_code_fetcher import get_translated_python_code_from_github
from code_translation.process_book_code import get_blocks_with_chapter, extract_block_structs_and_functions, \
    _format_blocks_text, extract_entities_usage, find_related_definitions_for_chapter, filter_out_older_chapters, \
    get_translated_algorithms, _format_translated_blocks, find_related_definitions, extract_block_chapter
from code_translation.prompts import update_descriptions_prompt, translate_julia_code_prompt, translate_example_prompt
from pdf_parsing.extract_algorithms_and_examples import extract_algorithms_and_examples, extract_algorithms, \
    extract_examples

PROMPTS_DIR = Path("prompts")

EXAMPLE_WITH_CODE_NUMBERS = [
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

TRANSLATED_CHAPTERS = [
    "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12", "14", "15", "16", "17", "20", "24",
]

CHAPTERS_TO_TRANSLATE = ["13", "18", "19", "21", "22", "23", "25", "26", "27", "E"]

TRANSLATED_ALGOS_PATH = Path("translated_algorithms.json")

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

    return translate_julia_code_prompt.format(
        _format_blocks_text(julia_chapter_code),
        _format_translated_blocks(translated_algorithms),
    )


def build_translate_example_prompt(example_number, blocks):
    """Build a prompt to translate a single example block to Python."""
    extract_block_structs_and_functions(blocks)
    extract_entities_usage(blocks)

    example = extract_examples([example_number], blocks)[0]

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
    translated_examples = get_translated_algorithms(filtered_related_algorithms, True)

    return translate_example_prompt.format(
        f"{example['caption']} \n\n {example['text']} \n\n",
        "\n".join(f"{translated['translated']} \n\n" for translated in translated_examples) or "",
    )


if __name__ == "__main__":
    # Configurable defaults for paths/output locations.
    parser = argparse.ArgumentParser(description="Build translation prompts from the Decision Making PDF.")
    parser.add_argument("--pdf-path", default="dm.pdf", help="Path to the source PDF (default: dm.pdf)")
    parser.add_argument("--prompts-dir", default="prompts", help="Output directory for prompts (default: prompts)")
    parser.add_argument(
        "--translated-algorithms-json",
        default="translated_algorithms.json",
        help="Path to translated algorithms JSON (default: translated_algorithms.json)",
    )
    args = parser.parse_args()

    pdf_path = args.pdf_path
    prompts_dir = Path(args.prompts_dir)
    TRANSLATED_ALGOS_PATH = Path(args.translated_algorithms_json)


    blocks = extract_algorithms_and_examples(pdf_path)

    julia_code = extract_algorithms(blocks)

    prompts_dir.mkdir(parents=True, exist_ok=True)
    for chapter in TRANSLATED_CHAPTERS:
        prompt = build_update_descriptions_prompt(chapter, julia_code)
        with open(prompts_dir / "update_description" / f"chapter_{chapter}_code_translation.txt", "w", encoding="utf-8") as f:
            f.write(prompt)

    for chapter in CHAPTERS_TO_TRANSLATE:
        prompt = build_translate_python_code_prompt(chapter, julia_code)
        with open(prompts_dir / "translate_algorithms" / f"chapter_{chapter}_translation.txt", "w", encoding="utf-8") as f:
            f.write(prompt)

    for example in EXAMPLE_WITH_CODE_NUMBERS:
        prompt = build_translate_example_prompt(example, blocks)
        with open(prompts_dir / "translate_examples" / f"{example.replace(' ', '_')}_translation.txt", "w", encoding="utf-8") as f:
            f.write(prompt)
