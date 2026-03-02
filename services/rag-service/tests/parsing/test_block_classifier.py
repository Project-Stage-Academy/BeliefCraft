from unittest.mock import MagicMock

from pipeline.parsing.block_classifier import BlockProcessor


def test_determine_block_type():
    # Check if the block type is correctly determined based on the text
    processor = BlockProcessor("dummy.pdf")

    assert processor._determine_block_type("Algorithm 1.1") == "algorithm"
    assert processor._determine_block_type("Example A.5") == "example"
    assert processor._determine_block_type("Random text") == "other"


def test_extract_captions_empty_page():
    processor = BlockProcessor("dummy.pdf")
    mock_page = MagicMock()
    mock_page.get_text.return_value = {"blocks": []}

    captions = processor._extract_captions(mock_page)
    assert captions == []


def test_determine_block_type_extended():
    processor = BlockProcessor("dummy.pdf")

    assert processor._determine_block_type("Exercise 1.1") == "exercise"
    assert processor._determine_block_type("Figure 2.1") == "figure"
    assert processor._determine_block_type("Table 3.1") == "table"
    assert processor._determine_block_type("Equation (4.1)") == "other"


def test_process_text_block_logic():
    processor = BlockProcessor("dummy.pdf")
    block = {
        "lines": [{"spans": [{"text": "Algorithm 5.1. Quick Sort"}]}],
        "bbox": [10, 10, 100, 20],
    }
    res = processor._process_text_block(block)
    assert res is not None
    assert res["type"] == "algorithm"
    assert "Quick Sort" in res["content"]
