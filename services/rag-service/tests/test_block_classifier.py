from unittest.mock import MagicMock

from parsing.block_classifier import BlockProcessor


def test_determine_block_type():
    # Check if the block type is correctly determined based on the text
    processor = BlockProcessor("dummy.pdf")

    assert processor._determine_block_type("Algorithm 1.1") == "algorithm"
    assert processor._determine_block_type("Example A.5") == "example"
    assert processor._determine_block_type("Random text") == "other"


def test_extract_captions_empty_page():
    processor = BlockProcessor("dummy.pdf")
    mock_page = MagicMock()
    mock_page.get_text.return_value = {"blocks": []}  # An empty page with no blocks

    captions = processor._extract_captions(mock_page)
    assert captions == []
