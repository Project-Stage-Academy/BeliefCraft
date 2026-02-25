from __future__ import annotations

import argparse
from pathlib import Path
from typing import TYPE_CHECKING

from common.logging import get_logger
from pipeline.code_translation.constants import TRANSLATED_ALGOS_PATH, PromptConfig
from pipeline.code_translation.github_code_fetcher import GitHubCodeFetcher
from pipeline.code_translation.process_book_code import (
    Block,
    BookCodeProcessor,
    JuliaEntityExtractor,
    TranslatedAlgorithmStore,
    UsageIndexBuilder,
)
from pipeline.code_translation.prompts import PromptTemplates
from pipeline.parsing.block_processor import open_block_processor

if TYPE_CHECKING:
    from pipeline.parsing.block_processor import BlockProcessor


logger = get_logger(__name__)


class PromptBuilder:
    """Builds prompt strings for translation workflows."""

    def __init__(
        self,
        book_processor: BookCodeProcessor,
        github_fetcher: GitHubCodeFetcher,
        block_processor: BlockProcessor | None = None,
    ) -> None:
        self._book_processor = book_processor
        self._github_fetcher = github_fetcher
        self._block_processor = block_processor

    def build_update_descriptions_prompt(self, chapter: str, julia_code: list[Block]) -> str:
        """Build a prompt to update algorithm descriptions for a chapter."""
        julia_chapter_code = self._book_processor.get_blocks_with_chapter(
            julia_code, str(int(chapter))
        )
        self._book_processor.extract_block_structs_and_functions(julia_chapter_code)
        python_chapter_code = self._github_fetcher.get_translated_python_code(chapter)

        prompt = PromptTemplates.update_descriptions_prompt(
            self._book_processor.format_blocks_text(julia_chapter_code),
            python_chapter_code,
        )
        logger.info(
            "prompt_built", kind="update_descriptions", chapter=chapter, prompt_chars=len(prompt)
        )
        return prompt

    def _parse_chapter_number(self, chapter: str) -> str:
        try:
            return str(int(chapter))
        except ValueError:
            return chapter

    def _collect_related_algorithms_for_chapter(
        self, chapter: str, julia_chapter_code: list[Block], julia_code: list[Block]
    ) -> list[str]:
        related_entities = self._book_processor.find_related_definitions_for_chapter(
            julia_chapter_code, julia_code
        )
        related_algorithms = {
            entity[1] for entities in related_entities.values() for entity in entities
        }
        return self._book_processor.filter_out_older_chapters(related_algorithms, chapter)

    def build_translate_python_code_prompt(self, chapter: str, julia_code: list[Block]) -> str:
        """Build a prompt to translate Julia algorithms in a chapter to Python."""
        self._book_processor.extract_block_structs_and_functions(julia_code)
        self._book_processor.extract_entities_usage(julia_code)

        chapter_number = self._parse_chapter_number(chapter)

        julia_chapter_code = self._book_processor.get_blocks_with_chapter(
            julia_code, chapter_number
        )
        filtered_related_algorithms = self._collect_related_algorithms_for_chapter(
            chapter, julia_chapter_code, julia_code
        )
        translated_algorithms = self._book_processor.get_translated_algorithms(
            filtered_related_algorithms
        )

        prompt = PromptTemplates.translate_julia_code_prompt(
            self._book_processor.format_blocks_text(julia_chapter_code),
            self._book_processor.format_translated_blocks(translated_algorithms),
        )
        logger.info(
            "prompt_built", kind="translate_algorithms", chapter=chapter, prompt_chars=len(prompt)
        )
        return prompt

    def _get_example_or_raise(self, example_number: str, blocks: list[Block]) -> dict[str, object]:
        if not self._block_processor:
            raise ValueError("BlockProcessor is required to extract examples")

        examples = self._block_processor.extract_examples([example_number], blocks)
        if not examples or not examples[0]:
            logger.warning("example_not_found", example_number=example_number)
            raise ValueError(f"Example with number {example_number} not found")

        return dict(examples[0])

    def _collect_related_algorithms_for_example(
        self, example_number: str, blocks: list[Block]
    ) -> list[str]:
        related_entities = self._book_processor.find_related_definitions(example_number, blocks)
        related_algorithms = {entity[1] for entity in related_entities}
        return self._book_processor.filter_out_older_chapters(
            related_algorithms,
            self._book_processor.extract_block_chapter(example_number),
        )

    def _format_translate_example_prompt(
        self, example: dict[str, object], translated_examples: list[dict[str, str]]
    ) -> str:
        translated_text = "\n".join(
            f"{translated['translated']} \n\n" for translated in translated_examples
        )
        return PromptTemplates.translate_example_prompt(
            f"{example['caption']} \n\n {example['text']} \n\n",
            translated_text or "",
        )

    def build_translate_example_prompt(self, example_number: str, blocks: list[Block]) -> str:
        """Build a prompt to translate a single example block to Python."""
        self._book_processor.extract_block_structs_and_functions(blocks)
        self._book_processor.extract_entities_usage(blocks)

        example = self._get_example_or_raise(example_number, blocks)
        filtered_related_algorithms = self._collect_related_algorithms_for_example(
            example_number, blocks
        )
        translated_examples = self._book_processor.get_translated_algorithms(
            filtered_related_algorithms, True
        )

        prompt = self._format_translate_example_prompt(example, translated_examples)
        logger.info(
            "prompt_built",
            kind="translate_example",
            example_number=example_number,
            prompt_chars=len(prompt),
        )
        return prompt


if __name__ == "__main__":
    # Configurable defaults for paths/output locations.
    config = PromptConfig()
    parser = argparse.ArgumentParser(
        description="Build translation prompts from the Decision Making PDF."
    )
    parser.add_argument(
        "--pdf-path", default="dm.pdf", help="Path to the source PDF (default: dm.pdf)"
    )
    parser.add_argument(
        "--prompts-dir",
        default=config.prompts_dir,
        help=f"Output directory for prompts (default: {config.prompts_dir})",
    )
    parser.add_argument(
        "--translated-algorithms-json",
        default=str(TRANSLATED_ALGOS_PATH),
        help="Path to translated algorithms JSON (default: translated_algorithms.json)",
    )
    args = parser.parse_args()

    pdf_path = args.pdf_path
    prompts_dir = Path(args.prompts_dir)
    translated_algos_path = Path(args.translated_algorithms_json)

    with open_block_processor(pdf_path) as block_processor:
        builder = PromptBuilder(
            book_processor=BookCodeProcessor(
                translated_algos_path,
                JuliaEntityExtractor(),
                UsageIndexBuilder(),
                TranslatedAlgorithmStore(translated_algos_path),
            ),
            github_fetcher=GitHubCodeFetcher(
                "https://github.com/griffinbholt/decisionmaking-code-py"
            ),
            block_processor=block_processor,
        )

        blocks = block_processor.extract_algorithms_and_examples()

        julia_code = block_processor.extract_algorithms(blocks)

        prompts_dir.mkdir(parents=True, exist_ok=True)
        for chapter in config.translated_chapters:
            prompt = builder.build_update_descriptions_prompt(chapter, julia_code)
            with (
                prompts_dir / "update_description" / f"chapter_{chapter}_code_translation.txt"
            ).open("w", encoding="utf-8") as f:
                f.write(prompt)

        for chapter in config.chapters_to_translate:
            prompt = builder.build_translate_python_code_prompt(chapter, julia_code)
            with (prompts_dir / "translate_algorithms" / f"chapter_{chapter}_translation.txt").open(
                "w", encoding="utf-8"
            ) as f:
                f.write(prompt)

        for example in config.example_with_code_numbers:
            prompt = builder.build_translate_example_prompt(example, blocks)
            with (
                prompts_dir / "translate_examples" / f"{example.replace(' ', '_')}_translation.txt"
            ).open("w", encoding="utf-8") as f:
                f.write(prompt)
