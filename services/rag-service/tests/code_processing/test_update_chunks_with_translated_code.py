import json
import sys
from pathlib import Path

import pytest
from pipeline.code_processing.julia_code_translation import (
    update_chunks_with_translated_code as updater,
)


@pytest.mark.unit
def test_extract_entity_id_from_number() -> None:
    assert updater.extract_entity_id_from_number("Algorithm 1.1.") == "1.1"
    assert updater.extract_entity_id_from_number("Example 2.3.") == "2.3"
    assert updater.extract_entity_id_from_number("Algorithm") == ""


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

    updated = updater.update_algorithms(chunks, translated_algorithms)

    assert updated[0]["content"] == "New description\n\nprint('hi')"
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
    updated = updater.update_examples(chunks, translated_examples)

    assert updated[0]["content"] == "New description\n\nExample text"
    assert updated[1]["content"] == "leave"


@pytest.mark.unit
def test_parse_args_parses_required_options(monkeypatch: pytest.MonkeyPatch) -> None:
    argv = [
        "prog",
        "--chunks",
        "chunks.json",
        "--translated-algorithms",
        "algos.json",
        "--translated-examples",
        "examples.json",
        "--output",
        "output.json",
    ]
    monkeypatch.setattr(sys, "argv", argv)

    args = updater.parse_args()

    assert args.chunks == "chunks.json"
    assert args.translated_algorithms == "algos.json"
    assert args.translated_examples == "examples.json"
    assert args.output == "output.json"


@pytest.mark.unit
def test_load_helpers_read_json(tmp_path: Path) -> None:
    algorithms_path = tmp_path / "algorithms.json"
    examples_path = tmp_path / "examples.json"
    chunks_path = tmp_path / "chunks.json"

    algorithms_payload = [
        {
            "algorithm_number": "Algorithm 1.1.",
            "code": "print('hi')",
            "description": "Desc",
            "declarations": {"State": "struct State"},
        }
    ]
    examples_payload = [
        {
            "example_number": "Example 2.4.",
            "description": "Example description",
            "text": "Example text",
        }
    ]
    chunks_payload = [{"chunk_type": "algorithm", "entity_id": "1.1", "content": "old"}]

    algorithms_path.write_text(json.dumps(algorithms_payload), encoding="utf-8")
    examples_path.write_text(json.dumps(examples_payload), encoding="utf-8")
    chunks_path.write_text(json.dumps(chunks_payload), encoding="utf-8")

    assert updater.load_translated_algorithms(algorithms_path) == algorithms_payload
    assert updater.load_translated_examples(examples_path) == examples_payload
    assert updater.load_chunks(chunks_path) == chunks_payload


@pytest.mark.unit
def test_main_writes_updated_chunks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    output_path = tmp_path / "output.json"

    class Args:
        book_pdf = "book.pdf"
        ocr_dir = "ocr"
        chunks = "chunks.json"
        translated_algorithms = "algos.json"
        translated_examples = "examples.json"
        output = str(output_path)

    chunks: list[updater.Chunk] = [
        {"chunk_type": "algorithm", "entity_id": "1.1", "content": "old"},
        {"chunk_type": "example", "entity_id": "2.4", "content": "old"},
    ]
    translated_algorithms: list[updater.TranslatedAlgorithm] = [
        {
            "algorithm_number": "Algorithm 1.1.",
            "code": "print('hi')",
            "description": "New description",
            "declarations": {"State": "struct State"},
        }
    ]
    translated_examples: list[updater.TranslatedExample] = [
        {
            "example_number": "Example 2.4.",
            "description": "Example description",
            "text": "Example text",
        }
    ]

    monkeypatch.setattr(updater, "parse_args", lambda: Args())
    monkeypatch.setattr(updater, "load_chunks", lambda *_: chunks)
    monkeypatch.setattr(updater, "load_translated_algorithms", lambda *_: translated_algorithms)
    monkeypatch.setattr(updater, "load_translated_examples", lambda *_: translated_examples)

    updater.main()

    assert output_path.exists()
    output_data = json.loads(output_path.read_text(encoding="utf-8"))
    assert output_data[0]["content"] == "New description\n\nprint('hi')"
    assert output_data[1]["content"] == "Example description\n\nExample text"
