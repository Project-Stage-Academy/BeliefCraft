from unittest.mock import MagicMock

import pytest
from pipeline.code_translation.build_prompts import PromptBuilder


def test_build_update_descriptions_prompt_includes_sources():
    book_processor = MagicMock()
    book_processor.get_blocks_with_chapter.return_value = [
        {"caption": "Algorithm 1.1.", "text": "code"}
    ]
    book_processor.format_blocks_text.return_value = "BLOCKS"

    github_fetcher = MagicMock()
    github_fetcher.get_translated_python_code.return_value = "PYCODE"

    builder = PromptBuilder(book_processor=book_processor, github_fetcher=github_fetcher)

    prompt = builder.build_update_descriptions_prompt("01", [{"caption": "x", "text": "y"}])

    assert "BLOCKS" in prompt
    assert "PYCODE" in prompt
    book_processor.extract_block_structs_and_functions.assert_called_once()


def test_build_translate_example_prompt_missing_example():
    book_processor = MagicMock()
    github_fetcher = MagicMock()
    block_processor = MagicMock()
    block_processor.extract_examples.return_value = [None]

    builder = PromptBuilder(
        book_processor=book_processor,
        github_fetcher=github_fetcher,
        block_processor=block_processor,
    )

    with pytest.raises(ValueError, match="Example with number"):
        builder.build_translate_example_prompt("Example 1.1.", [])


def test_build_translate_example_prompt_includes_context():
    book_processor = MagicMock()
    book_processor.find_related_definitions.return_value = [("foo", "Algorithm 1.1.")]
    book_processor.filter_out_older_chapters.return_value = ["Algorithm 1.1."]
    book_processor.get_translated_algorithms.return_value = [{"translated": "def foo():\n    pass"}]

    block_processor = MagicMock()
    example = {"caption": "Example 1.1.", "text": "Example text", "block_type": "Example"}
    block_processor.extract_examples.return_value = [example]

    builder = PromptBuilder(
        book_processor=book_processor,
        github_fetcher=MagicMock(),
        block_processor=block_processor,
    )

    prompt = builder.build_translate_example_prompt("Example 1.1.", [{"caption": "x", "text": "y"}])

    assert "Example text" in prompt
    assert "def foo" in prompt
    book_processor.extract_block_structs_and_functions.assert_called_once()
    book_processor.extract_entities_usage.assert_called_once()
