import pytest
from pipeline.parsing.metadata_extractor import MetadataExtractor

def test_metadata_extractor_headers():
    extractor = MetadataExtractor()
    
    content = "CHAPTER 1 INTRODUCTION"
    meta = extractor.process_content_and_get_meta(content)
    assert meta["section_number"] == "1"
    assert "INTRODUCTION" in meta["section_title"]
    assert meta["force_new_chunk"] is True

    content = "1.1 Fundamental Concepts"
    meta = extractor.process_content_and_get_meta(content)
    assert meta["subsection_number"] == "1.1"
    assert "Fundamental Concepts" in meta["subsection_title"]

def test_metadata_extractor_references():
    extractor = MetadataExtractor()
    text = "As seen in Figure 1.1 and Table 2.2, also refer to Algorithm 3.3."
    refs = extractor.get_references(text)
    
    assert "1.1" in refs["referenced_figures"]
    assert "2.2" in refs["referenced_tables"]
    assert "3.3" in refs["referenced_algorithms"]