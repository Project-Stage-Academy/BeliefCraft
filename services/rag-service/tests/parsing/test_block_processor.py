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


def test_block_processor_simple():
    assert bp.BlockProcessor._extract_entity_id("Figure 10.5") == "10.5"

    assert bp.BlockType.ALGORITHM is not None


def _make_page(blocks: list[dict]) -> object:
    class _Page:
        def get_text(self, mode: str):
            assert mode == "dict"
            return {"blocks": blocks}

    return _Page()


def test_extract_captions_collects_right_column_lines_and_stops_on_large_gap():
    finder = bp.CaptionFinder(bp.algorithms_pattern, bp.example_pattern)
    page = _make_page(
        [
            {
                "lines": [
                    {
                        "bbox": (310, 10, 380, 20),
                        "spans": [{"text": "Algorithm 2.1."}],
                    },
                    {
                        "bbox": (310, 22, 430, 32),
                        "spans": [{"text": "A caption line"}],
                    },
                    {
                        "bbox": (310, 80, 440, 90),
                        "spans": [{"text": "Should be ignored"}],
                    },
                ]
            }
        ]
    )

    captions = finder.extract_captions(page)

    assert len(captions) == 1
    assert captions[0]["type"] == bp.BlockType.ALGORITHM.value
    assert captions[0]["text"] == "Algorithm 2.1. A caption line"
    assert tuple(captions[0]["bbox"]) == (310.0, 10.0, 430.0, 32.0)


def test_extract_captions_supports_algorithm_header_split_across_two_lines():
    finder = bp.CaptionFinder(bp.algorithms_pattern, bp.example_pattern)
    page = _make_page(
        [
            {
                "lines": [
                    {
                        "bbox": (305, 10, 360, 20),
                        "spans": [{"text": "Algorithm"}],
                    },
                    {
                        "bbox": (305, 23, 430, 33),
                        "spans": [{"text": "2.1. Split header"}],
                    },
                ]
            }
        ]
    )

    captions = finder.extract_captions(page)

    assert len(captions) == 1
    assert captions[0]["type"] == bp.BlockType.ALGORITHM.value
    assert captions[0]["text"] == "Algorithm 2.1. Split header"
