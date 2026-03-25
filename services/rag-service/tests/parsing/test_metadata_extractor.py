import pytest
from pipeline.parsing.metadata_extractor import MetadataExtractor


@pytest.fixture
def extractor():
    return MetadataExtractor()


def test_process_section_header(extractor):
    # Metadata extractor recognises markdown-style headers (#+) only.
    # "CHAPTER N TITLE" plain text is NOT recognised; use "# N TITLE".
    content = "# 1 INTRODUCTION"
    meta = extractor.process_content_and_get_meta(content)

    assert meta["section_number"] == "1"
    # The captured title is only the text after the number, without the number itself.
    assert meta["section_title"] == "INTRODUCTION"
    assert meta["force_new_chunk"] is True


def test_process_subsection_header(extractor):
    # Test subsection header extraction with markdown prefix
    content = "## 1.2 Probability Theory"
    meta = extractor.process_content_and_get_meta(content)

    assert meta["subsection_number"] == "1.2"
    assert meta["subsection_title"] == "Probability Theory"


def test_get_references(extractor):
    # Test extracting references
    text = "As seen in Figure 1.2 and Table 3.4, the results vary."
    refs = extractor.get_references(text)

    assert "1.2" in refs["referenced_figures"]
    assert "3.4" in refs["referenced_tables"]


def test_metadata_extractor_deep_hierarchy():
    extractor = MetadataExtractor()

    # Three-level hierarchy requires three-hash prefix "### N.N.N"
    content = "### 2.1.3 Advanced Optimization"
    meta = extractor.process_content_and_get_meta(content)
    assert meta.get("subsubsection_number") == "2.1.3"

    # Reset extractor to test section independently
    extractor2 = MetadataExtractor()
    content = "# 5 SUMMARY"
    meta = extractor2.process_content_and_get_meta(content)
    assert meta.get("section_number") == "5"


def test_metadata_extractor_all_references():
    extractor = MetadataExtractor()
    text = "Refer to Example 1.1, Exercise 4.2 and Equation (5.6)."
    refs = extractor.get_references(text)

    assert "1.1" in refs["referenced_examples"]
    assert "4.2" in refs["referenced_exercises"]
    assert "5.6" in refs["referenced_formulas"]
