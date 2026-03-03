import pytest
from pipeline.julia_code_translation import update_chunks_with_translated_code as updater


@pytest.mark.unit
def test_extract_entity_id_from_number() -> None:
    assert updater.extract_entity_id_from_number("Algorithm 1.1.") == "1.1"
    assert updater.extract_entity_id_from_number("Example 2.3.") == "2.3"
    assert updater.extract_entity_id_from_number("Algorithm") == ""


@pytest.mark.unit
def test_find_used_algorithms_filters_and_extracts() -> None:
    blocks: list[updater.Block] = [
        {
            "block_type": "Algorithm",
            "number": "Algorithm 3.2.",
            "caption": "",
            "text": "",
            "structs": {"State": ["Algorithm 1.1."]},
            "functions": {"step": ["Algorithm 1.1.", "Algorithm 9.9."]},
        },
        {
            "block_type": "Example",
            "number": "Example 1.1.",
            "caption": "",
            "text": "",
            "structs": {"Ignored": ["Algorithm 1.1."]},
            "functions": {"ignored": ["Algorithm 1.1."]},
        },
    ]

    used_structs, used_functions = updater.find_used_algorithms(blocks, "Algorithm 1.1.")

    assert used_structs == {"State": ["3.2"]}
    assert used_functions == {"step": ["3.2"]}


@pytest.mark.unit
def test_update_algorithms_merges_translations_and_usage() -> None:
    chunks: list[updater.Chunk] = [
        {"chunk_type": "algorithm", "entity_id": "1.1", "content": "old"},
        {"chunk_type": "text", "entity_id": "x", "content": "leave"},
    ]
    translated_algorithms: list[updater.TranslatedAlgorithm] = [
        {
            "algorithm_number": "Algorithm 1.1.",
            "code": "print('hi')",
            "description": "New description",
            "declarations": {"State": "struct State"},
        }
    ]
    blocks: list[updater.Block] = [
        {
            "block_type": "Algorithm",
            "number": "Algorithm 2.1.",
            "caption": "",
            "text": "",
            "structs": {"State": ["Algorithm 1.1."]},
            "functions": {"step": ["Algorithm 1.1."]},
        }
    ]

    updated = updater.update_algorithms(chunks, translated_algorithms, blocks)

    assert updated[0]["content"] == "New description\n\nprint('hi')"
    assert updated[0]["declarations"] == ["struct State"]
    assert updated[0]["used_structs"] == {"State": ["2.1"]}
    assert updated[0]["used_functions"] == {"step": ["2.1"]}
    assert updated[1]["content"] == "leave"


@pytest.mark.unit
def test_update_examples_merges_translations_and_usage() -> None:
    chunks: list[updater.Chunk] = [
        {"chunk_type": "example", "entity_id": "2.4", "content": "old"},
        {"chunk_type": "text", "entity_id": "x", "content": "leave"},
    ]
    translated_examples: list[updater.TranslatedExample] = [
        {
            "example_number": "Example 2.4.",
            "description": "New description",
            "text": "Example text",
        }
    ]
    blocks: list[updater.Block] = [
        {
            "block_type": "Algorithm",
            "number": "Algorithm 9.9.",
            "caption": "",
            "text": "",
            "structs": {"State": ["Example 2.4."]},
            "functions": {"step": ["Example 2.4."]},
        }
    ]

    updated = updater.update_examples(chunks, translated_examples, blocks)

    assert updated[0]["content"] == "New description\n\nExample text"
    assert updated[0]["used_structs"] == {"State": ["9.9"]}
    assert updated[0]["used_functions"] == {"step": ["9.9"]}
    assert updated[1]["content"] == "leave"
