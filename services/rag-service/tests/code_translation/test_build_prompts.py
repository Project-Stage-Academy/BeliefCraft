from unittest.mock import MagicMock

import pytest

from code_translation import build_prompts
from code_translation.build_prompts import PromptBuilder


def test_build_update_descriptions_prompt_includes_sources():
    book_processor = MagicMock()
    book_processor.get_blocks_with_chapter.return_value = [{"caption": "Algorithm 1.1.", "text": "code"}]
    book_processor.format_blocks_text.return_value = "BLOCKS"

    github_fetcher = MagicMock()
    github_fetcher.get_translated_python_code.return_value = "PYCODE"

    builder = PromptBuilder(book_processor=book_processor, github_fetcher=github_fetcher)

    prompt = builder.build_update_descriptions_prompt("01", [{"caption": "x", "text": "y"}])

    assert "BLOCKS" in prompt
    assert "PYCODE" in prompt
    book_processor.extract_block_structs_and_functions.assert_called_once()


def test_build_translate_example_prompt_missing_example(monkeypatch):
    book_processor = MagicMock()
    github_fetcher = MagicMock()
    builder = PromptBuilder(book_processor=book_processor, github_fetcher=github_fetcher)

    monkeypatch.setattr(build_prompts, "extract_examples", lambda *args, **kwargs: [None])

    with pytest.raises(ValueError, match="Example with number"):
        builder.build_translate_example_prompt("Example 1.1.", [])


def test_build_translate_example_prompt_includes_context(monkeypatch):
    book_processor = MagicMock()
    book_processor.find_related_definitions.return_value = [("foo", "Algorithm 1.1.")]
    book_processor.filter_out_older_chapters.return_value = ["Algorithm 1.1."]
    book_processor.get_translated_algorithms.return_value = [{"translated": "def foo():\n    pass"}]

    builder = PromptBuilder(book_processor=book_processor, github_fetcher=MagicMock())

    example = {"caption": "Example 1.1.", "text": "Example text", "block_type": "Example"}
    monkeypatch.setattr(build_prompts, "extract_examples", lambda *args, **kwargs: [example])

    prompt = builder.build_translate_example_prompt("Example 1.1.", [{"caption": "x", "text": "y"}])

    assert "Example text" in prompt
    assert "def foo" in prompt
    book_processor.extract_block_structs_and_functions.assert_called_once()
    book_processor.extract_entities_usage.assert_called_once()

