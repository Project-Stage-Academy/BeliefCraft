import pytest
from src.parsing.metadata_extractor import MetadataExtractor


@pytest.fixture
def extractor():
    return MetadataExtractor()


def test_process_section_header(extractor):
    # Test section header extraction
    content = "CHAPTER 1 INTRODUCTION"
    meta = extractor.process_content_and_get_meta(content)

    assert meta["section_number"] == "1"
    assert meta["section_title"] == "1 INTRODUCTION"
    assert meta["force_new_chunk"] is True


def test_process_subsection_header(extractor):
    # Test subsection header extraction
    content = "1.2 Probability Theory"
    meta = extractor.process_content_and_get_meta(content)

    assert meta["subsection_number"] == "1.2"
    assert meta["subsection_title"] == "1.2 Probability Theory"


def test_get_references(extractor):
    # Test extracting references
    text = "As seen in Figure 1.2 and Table 3.4, the results vary."
    refs = extractor.get_references(text)

    assert "1.2" in refs["referenced_figures"]
    assert "3.4" in refs["referenced_tables"]
