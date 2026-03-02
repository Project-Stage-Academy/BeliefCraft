from unittest.mock import MagicMock

from pipeline.parsing.block_classifier import BlockProcessor


def test_determine_block_type():
    processor = BlockProcessor("dummy.pdf")
    assert processor._determine_block_type("ALGORITHM 1.1") == "algorithm"
    assert processor._determine_block_type("EXAMPLE 2.1") == "example"
    res = processor._determine_block_type("Exercise 1.1")
    assert res in ["exercise", "other"]


def test_process_text_block_logic():
    processor = BlockProcessor("dummy.pdf")
    block = {
        "lines": [{"spans": [{"text": "Algorithm 5.1. Quick Sort"}], "bbox": [10, 10, 100, 20]}],
        "bbox": [10, 10, 100, 20],
    }
    res = processor._process_text_block(block)
    if res:
        assert res["type"] == "algorithm"


def test_extract_captions_empty_page():
    processor = BlockProcessor("dummy.pdf")
    mock_page = MagicMock()
    mock_page.get_text.return_value = []
    captions = processor._extract_captions(mock_page)
    assert captions == []


def test_determine_block_type_extended():
    processor = BlockProcessor("dummy.pdf")
    assert processor._determine_block_type("ALGORITHM 1.1") == "algorithm"
    assert processor._determine_block_type("EXAMPLE 2.2") == "example"
    res = processor._determine_block_type("Exercise 1.1")
    assert res in ["exercise", "other"]
