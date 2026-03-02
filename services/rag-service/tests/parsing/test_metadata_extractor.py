import pytest
from pipeline.parsing.metadata_extractor import MetadataExtractor


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


def test_metadata_extractor_deep_hierarchy():
    extractor = MetadataExtractor()

    content = "2.1.3 Advanced Optimization"
    meta = extractor.process_content_and_get_meta(content)
    assert meta.get("subsubsection_number") == "2.1.3"

    content = "PART I: INTRODUCTION"
    meta = extractor.process_content_and_get_meta(content)
    assert isinstance(meta, dict)


def test_metadata_extractor_all_references():
    extractor = MetadataExtractor()
    text = "Refer to Example 1.1, Exercise 4.2 and Equation (5.6)."
    refs = extractor.get_references(text)

    assert "1.1" in refs["referenced_examples"]
    assert "4.2" in refs["referenced_exercises"]
    assert "5.6" in refs["referenced_formulas"]
