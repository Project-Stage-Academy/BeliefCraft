"""
Characterization tests for MetadataExtractor.

These tests lock the *current* behaviour of the class so that future
refactors cannot silently break it.  Every test carries a docstring that
states exactly which invariant it encodes.
"""

import pytest
from pipeline.parsing.metadata_extractor import MetadataExtractor


@pytest.fixture()
def extractor() -> MetadataExtractor:
    return MetadataExtractor()


# ---------------------------------------------------------------------------
# Header detection
# ---------------------------------------------------------------------------


def test_section_header_sets_section_fields(extractor: MetadataExtractor) -> None:
    """Locks: a single-hash header (# N TITLE) sets section_number and section_title,
    resets subsection/subsubsection, and sets force_new_chunk=True.
    """
    meta = extractor.process_content_and_get_meta("# 3 Foundations")

    assert meta["section_number"] == "3"
    assert meta["section_title"] == "Foundations"
    assert meta["force_new_chunk"] is True
    assert meta["subsection_number"] is None
    assert meta["subsection_title"] is None
    assert meta["subsubsection_number"] is None
    assert meta["subsubsection_title"] is None


def test_subsection_header_sets_subsection_fields(extractor: MetadataExtractor) -> None:
    """Locks: a double-hash header (## N.M TITLE) sets subsection fields and resets subsubsection"""
    meta = extractor.process_content_and_get_meta("## 2.3 Probability")

    assert meta["subsection_number"] == "2.3"
    assert meta["subsection_title"] == "Probability"
    assert meta["force_new_chunk"] is True
    assert meta["subsubsection_number"] is None
    assert meta["subsubsection_title"] is None


def test_subsubsection_header_sets_subsubsection_fields(extractor: MetadataExtractor) -> None:
    """Locks: a triple-hash header (### N.M.K TITLE) sets subsubsection fields only."""
    meta = extractor.process_content_and_get_meta("### 1.2.3 Advanced")

    assert meta["subsubsection_number"] == "1.2.3"
    assert meta["subsubsection_title"] == "Advanced"
    assert meta["force_new_chunk"] is True


def test_section_header_resets_subsection_and_subsubsection(extractor: MetadataExtractor) -> None:
    """Locks: a new section header clears both subsection AND subsubsection state."""
    extractor.process_content_and_get_meta("## 1.1 Old Sub")
    extractor.process_content_and_get_meta("### 1.1.1 Old SubSub")

    meta = extractor.process_content_and_get_meta("# 2 New Section")

    assert meta["section_number"] == "2"
    assert meta["subsection_number"] is None
    assert meta["subsection_title"] is None
    assert meta["subsubsection_number"] is None
    assert meta["subsubsection_title"] is None


def test_subsection_header_resets_only_subsubsection(extractor: MetadataExtractor) -> None:
    """Locks: a new subsection header only resets subsubsection, leaving section intact."""
    extractor.process_content_and_get_meta("# 1 Section")
    extractor.process_content_and_get_meta("### 1.1.1 Old SubSub")

    meta = extractor.process_content_and_get_meta("## 1.2 New Sub")

    assert meta["section_number"] == "1"
    assert meta["subsection_number"] == "1.2"
    assert meta["subsubsection_number"] is None
    assert meta["subsubsection_title"] is None


# ---------------------------------------------------------------------------
# set_part()
# ---------------------------------------------------------------------------


def test_set_part_resets_all_hierarchy_levels() -> None:
    """Locks: set_part() resets section, subsection, and subsubsection to None."""
    extractor = MetadataExtractor()
    extractor.process_content_and_get_meta("# 5 Some Section")
    extractor.process_content_and_get_meta("## 5.1 Some Sub")
    extractor.process_content_and_get_meta("### 5.1.2 Some SubSub")

    extractor.set_part("II", "Advanced Topics")
    meta = extractor.get_meta()

    assert meta["part"] == "II"
    assert meta["part_title"] == "Advanced Topics"
    assert meta["section_number"] is None
    assert meta["section_title"] is None
    assert meta["subsection_number"] is None
    assert meta["subsection_title"] is None
    assert meta["subsubsection_number"] is None
    assert meta["subsubsection_title"] is None


def test_set_part_trims_whitespace_from_title() -> None:
    """Locks: set_part() strips leading/trailing whitespace from part_title."""
    extractor = MetadataExtractor()

    extractor.set_part("I", "  Foundations  ")

    assert extractor.current_part_title == "Foundations"


# ---------------------------------------------------------------------------
# Non-header lines → clean_content
# ---------------------------------------------------------------------------


def test_non_header_lines_returned_as_clean_content(extractor: MetadataExtractor) -> None:
    """Locks: lines without a markdown header prefix pass through as clean_content
    and do NOT set force_new_chunk.
    """
    meta = extractor.process_content_and_get_meta("Ordinary paragraph text.")

    assert meta["clean_content"] == "Ordinary paragraph text."
    assert meta["force_new_chunk"] is False


def test_part_only_line_is_not_treated_as_header(extractor: MetadataExtractor) -> None:
    """Locks: a bare 'PART I' line (no leading #) is preserved as clean_content and
    does not trigger header detection.
    """
    meta = extractor.process_content_and_get_meta("PART I")

    assert "PART I" in meta["clean_content"]
    assert meta["force_new_chunk"] is False
    assert meta["section_number"] is None


def test_header_line_stripped_body_lines_kept(extractor: MetadataExtractor) -> None:
    """Locks: when a block contains both a header line and body text, the header line
    is removed from clean_content while body lines are preserved.
    """
    content = "# 1 Introduction\nThis is the body text.\nMore body."
    meta = extractor.process_content_and_get_meta(content)

    assert meta["section_number"] == "1"
    assert "# 1 Introduction" not in meta["clean_content"]
    assert "This is the body text." in meta["clean_content"]
    assert "More body." in meta["clean_content"]


def test_empty_lines_stripped_from_clean_content(extractor: MetadataExtractor) -> None:
    """Locks: empty lines within a block are dropped from clean_content."""
    meta = extractor.process_content_and_get_meta("Line one\n\nLine two")

    assert "" not in meta["clean_content"].split("\n")
    assert "Line one" in meta["clean_content"]
    assert "Line two" in meta["clean_content"]


# ---------------------------------------------------------------------------
# update_meta=False
# ---------------------------------------------------------------------------


def test_update_meta_false_does_not_mutate_state(extractor: MetadataExtractor) -> None:
    """Locks: when update_meta=False, headers are detected (force_new_chunk may fire)
    but the extractor's own state fields are NOT updated.
    """
    extractor.process_content_and_get_meta("# 1 Original")

    extractor.process_content_and_get_meta("# 2 New Section", update_meta=False)

    meta = extractor.get_meta()
    assert meta["section_number"] == "1"
    assert meta["section_title"] == "Original"


# ---------------------------------------------------------------------------
# get_references()
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text, field, expected_id",
    [
        # figures
        ("See Figure 3.1 for details.", "referenced_figures", "3.1"),
        # tables
        ("Table 2.4 shows the results.", "referenced_tables", "2.4"),
        # formulas / equations
        ("Eq. (5.6) defines the term.", "referenced_formulas", "5.6"),
        # algorithms
        ("Algorithm 1.2 describes the procedure.", "referenced_algorithms", "1.2"),
        # examples
        ("Example 1.1 illustrates this.", "referenced_examples", "1.1"),
        # exercises
        ("Exercise 4.2 is left to the reader.", "referenced_exercises", "4.2"),
        # sections
        ("Section 2.3 covers entropy.", "referenced_sections", "2.3"),
        # alphanumeric entity id
        ("Figure A.10 is referenced.", "referenced_figures", "A.10"),
    ],
)
def test_get_references_extracts_expected_fields(
    extractor: MetadataExtractor, text: str, field: str, expected_id: str
) -> None:
    """Locks: get_references() finds each entity type and returns uppercase IDs."""
    refs = extractor.get_references(text)

    assert expected_id.upper() in refs[field]


def test_get_references_uppercases_all_ids(extractor: MetadataExtractor) -> None:
    """Locks: all reference IDs are uppercased in the output."""
    refs = extractor.get_references("See figure a.1 and exercise b.2.")

    assert all(v == v.upper() for field_list in refs.values() for v in field_list)


def test_get_references_returns_empty_dict_for_empty_string(
    extractor: MetadataExtractor,
) -> None:
    """Locks: get_references('') returns an empty dict (no keys)."""
    refs = extractor.get_references("")

    assert refs == {}


def test_get_references_deduplicates_repeated_ids(extractor: MetadataExtractor) -> None:
    """Locks: a reference that appears twice in the text is returned only once."""
    refs = extractor.get_references("Figure 1.1 and Figure 1.1 again.")

    assert refs["referenced_figures"].count("1.1") == 1


def test_get_references_strips_dollar_signs_before_matching(
    extractor: MetadataExtractor,
) -> None:
    """Locks: dollar-sign LaTeX delimiters are stripped before regex matching so
    references inside math blocks are still captured.
    """
    refs = extractor.get_references("$Figure 4.1$ is relevant.")

    assert "4.1" in refs["referenced_figures"]
