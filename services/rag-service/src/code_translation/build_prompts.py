import argparse
from pathlib import Path

from code_translation.github_code_fetcher import GitHubCodeFetcher
from code_translation.process_book_code import BookCodeProcessor
from code_translation.prompts import PromptTemplates
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


class PromptBuilder:
    def __init__(
        self,
        book_processor: BookCodeProcessor | None = None,
        github_fetcher: GitHubCodeFetcher | None = None,
    ) -> None:
        self._book_processor = book_processor or BookCodeProcessor()
        self._github_fetcher = github_fetcher or GitHubCodeFetcher(
            "https://github.com/griffinbholt/decisionmaking-code-py"
        )

    def build_update_descriptions_prompt(self, chapter, julia_code):
        """Build a prompt to update algorithm descriptions for a chapter."""
        julia_chapter_code = self._book_processor.get_blocks_with_chapter(julia_code, str(int(chapter)))
        self._book_processor.extract_block_structs_and_functions(julia_chapter_code)
        python_chapter_code = self._github_fetcher.get_translated_python_code(chapter, None)

        return PromptTemplates.update_descriptions_prompt.format(
            self._book_processor.format_blocks_text(julia_chapter_code),
            python_chapter_code,
        )

    def build_translate_python_code_prompt(self, chapter, julia_code):
        """Build a prompt to translate Julia algorithms in a chapter to Python."""
        self._book_processor.extract_block_structs_and_functions(julia_code)
        self._book_processor.extract_entities_usage(julia_code)

        try:
            chapter_number = str(int(chapter))
        except ValueError:
            chapter_number = chapter

        julia_chapter_code = self._book_processor.get_blocks_with_chapter(julia_code, chapter_number)
        related_entities = self._book_processor.find_related_definitions_for_chapter(julia_chapter_code, julia_code)

        related_algorithms = set()
        for entities in related_entities.values():
            for entity in entities:
                related_algorithms.add(entity[1])
        filtered_related_algorithms = self._book_processor.filter_out_older_chapters(related_algorithms, chapter)
        translated_algorithms = self._book_processor.get_translated_algorithms(filtered_related_algorithms)

        return PromptTemplates.translate_julia_code_prompt.format(
            self._book_processor.format_blocks_text(julia_chapter_code),
            self._book_processor.format_translated_blocks(translated_algorithms),
        )

    def build_translate_example_prompt(self, example_number, blocks):
        """Build a prompt to translate a single example block to Python."""
        self._book_processor.extract_block_structs_and_functions(blocks)
        self._book_processor.extract_entities_usage(blocks)

        example = extract_examples([example_number], blocks)[0]

        if not example:
            raise ValueError(f"Example with number {example_number} not found")

        related_entities = self._book_processor.find_related_definitions(example_number, blocks)
        related_algorithms = set()
        for entity in related_entities:
            related_algorithms.add(entity[1])

        filtered_related_algorithms = self._book_processor.filter_out_older_chapters(
            related_algorithms,
            self._book_processor.extract_block_chapter(example_number),
        )
        translated_examples = self._book_processor.get_translated_algorithms(filtered_related_algorithms, True)

        return PromptTemplates.translate_example_prompt.format(
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

    builder = PromptBuilder(book_processor=BookCodeProcessor(TRANSLATED_ALGOS_PATH))

    blocks = extract_algorithms_and_examples(pdf_path)

    julia_code = extract_algorithms(blocks)

    prompts_dir.mkdir(parents=True, exist_ok=True)
    for chapter in TRANSLATED_CHAPTERS:
        prompt = builder.build_update_descriptions_prompt(chapter, julia_code)
        with open(prompts_dir / "update_description" / f"chapter_{chapter}_code_translation.txt", "w", encoding="utf-8") as f:
            f.write(prompt)

    for chapter in CHAPTERS_TO_TRANSLATE:
        prompt = builder.build_translate_python_code_prompt(chapter, julia_code)
        with open(prompts_dir / "translate_algorithms" / f"chapter_{chapter}_translation.txt", "w", encoding="utf-8") as f:
            f.write(prompt)

    for example in EXAMPLE_WITH_CODE_NUMBERS:
        prompt = builder.build_translate_example_prompt(example, blocks)
        with open(prompts_dir / "translate_examples" / f"{example.replace(' ', '_')}_translation.txt", "w", encoding="utf-8") as f:
            f.write(prompt)
