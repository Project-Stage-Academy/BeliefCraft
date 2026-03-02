import json
from pathlib import Path

import pytest
from pipeline.parsing import block_processor as bp

fitz = pytest.importorskip("fitz")


def test_caption_finder_classifies_text_and_block():
    finder = bp.CaptionFinder(bp.algorithms_pattern, bp.example_pattern)

    assert finder.classify_text("Algorithm 2.1.") == bp.BlockType.ALGORITHM.value
    assert finder.classify_text("Example 3.1.") == bp.BlockType.EXAMPLE.value
    assert finder.classify_text("Something else") == bp.BlockType.OTHER.value

    block = {"lines": [{"spans": [{"text": "Example 3.1."}]}]}
    assert finder.classify_block(block) == bp.BlockType.EXAMPLE.value


def test_extract_entity_id_from_caption():
    assert bp.BlockProcessor._extract_entity_id("Algorithm 2.1. Foo") == "2.1"
    assert bp.BlockProcessor._extract_entity_id("No number here") is None


def test_strip_html_and_caption_key():
    assert bp.OcrCaptionRepository.strip_html("<b>Example</b> 2.1.") == "Example 2.1."
    assert bp.OcrCaptionRepository.caption_key_from_caption("Algorithm 2.1.") == "Algorithm 2.1."
    assert bp.OcrCaptionRepository.caption_key_from_caption("Example") == "Example"


def test_get_example_caption_from_page(tmp_path: Path):
    repo = bp.OcrCaptionRepository(tmp_path)
    page = {
        "prunedResult": {
            "parsing_res_list": [
                {"block_content": "Example 2.1. Some text"},
                {"block_content": "Other content"},
            ]
        }
    }

    result = repo.get_example_caption(page, "Example 2.1.")

    assert result == "Example 2.1. Some text"


def test_get_algorithm_caption_from_json_files(tmp_path: Path):
    data = [
        {
            "prunedResult": {
                "parsing_res_list": [{"block_content": "Intro Algorithm 3.1. Caption text"}]
            }
        }
    ]
    json_path = tmp_path / "001.json"
    json_path.write_text(json.dumps(data), encoding="utf-8")

    repo = bp.OcrCaptionRepository(tmp_path)

    result = repo.get_algorithm_caption("Algorithm 3.1.")

    assert result == "Algorithm 3.1. Caption text"


def test_is_inside_bbox_normalizes_bounds(tmp_path: Path):
    repo = bp.OcrCaptionRepository(tmp_path)
    hydrator = bp.BlockHydrator(repo)

    assert hydrator._is_inside_bbox(
        (0, 0, 576, 648),
        (0, 0, 1094, 1235),
    )
    assert not hydrator._is_inside_bbox(
        (0, 0, 576, 648),
        (0, 0, 2000, 1235),
    )


def test_block_processor_edge_cases():
    from pipeline.parsing import block_processor as bp

    assert bp.BlockProcessor._extract_entity_id("Figure 10.5") == "10.5"
    assert bp.BlockProcessor._extract_entity_id("Table 2.1") == "2.1"

    assert bp.BlockType.ALGORITHM.value.lower() == "algorithm"


def test_block_processor_is_inside_logic():
    from pipeline.parsing import block_processor as bp

    processor = bp.BlockProcessor.__new__(bp.BlockProcessor)

    assert processor._is_inside_bbox((10, 10, 50, 50), (0, 0, 100, 100)) is True
    assert processor._is_inside_bbox((100, 100, 150, 150), (0, 0, 50, 50)) is False
