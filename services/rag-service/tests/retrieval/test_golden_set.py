"""Tests for golden_set.py loader."""

from .golden_set import _generate_description, load_by_split, load_golden_set
from .models import RAGTestCase


def test_load_golden_set_returns_list_of_rag_test_cases():
    """Golden set loader returns list of RAGTestCase instances."""
    cases = load_golden_set()
    assert isinstance(cases, list)
    assert len(cases) > 0
    assert all(isinstance(case, RAGTestCase) for case in cases)


def test_load_golden_set_preserves_id_and_split():
    """Loader preserves id and split from JSON."""
    cases = load_golden_set()
    assert any(case.id == "tc_001" for case in cases)
    first_case = next(c for c in cases if c.id == "tc_001")
    assert first_case.split in ("validation", "test", None)


def test_load_golden_set_maps_question_to_base_query():
    """JSON 'question' field becomes base_query in RAGTestCase."""
    cases = load_golden_set()
    first_case = cases[0]
    assert len(first_case.base_query) > 0
    assert isinstance(first_case.base_query, str)


def test_load_golden_set_includes_paraphrases():
    """Paraphrases list is populated from JSON."""
    cases = load_golden_set()
    first_case = cases[0]
    assert isinstance(first_case.paraphrases, list)
    # Note: paraphrases may be empty if not generated
    assert all(isinstance(p, str) for p in first_case.paraphrases)


def test_load_golden_set_includes_expected_chunks():
    """Expected chunks list is populated with chunk_id and pdf_block_ids."""
    cases = load_golden_set()
    first_case = cases[0]
    assert isinstance(first_case.expected_chunks, list)
    assert len(first_case.expected_chunks) >= 1

    for chunk in first_case.expected_chunks:
        assert hasattr(chunk, "chunk_id")
        assert hasattr(chunk, "pdf_block_ids")
        assert isinstance(chunk.chunk_id, str)
        assert isinstance(chunk.pdf_block_ids, list)
        # Chunk IDs should be stable parser IDs, not UUIDs
        assert "_" in chunk.chunk_id or chunk.chunk_id.startswith("text")


def test_load_golden_set_generates_description():
    """Description is generated from question text."""
    cases = load_golden_set()
    first_case = cases[0]
    assert isinstance(first_case.description, str)
    # Description should be truncated version of base_query
    assert len(first_case.description) <= 80


def test_generate_description_truncates_long_questions():
    """Description generator truncates at max_length with ellipsis."""
    long_text = "A" * 100
    desc = _generate_description(long_text, max_length=50)
    assert len(desc) == 50
    assert desc.endswith("...")


def test_generate_description_preserves_short_questions():
    """Short questions are not truncated."""
    short_text = "Short question?"
    desc = _generate_description(short_text, max_length=80)
    assert desc == short_text


def test_load_by_split_filters_validation():
    """load_by_split returns only validation cases."""
    validation_cases = load_by_split("validation")
    assert all(case.split == "validation" for case in validation_cases)
    # Validation cases should exist in golden set
    assert len(validation_cases) > 0


def test_load_by_split_filters_test():
    """load_by_split returns only test cases if they exist."""
    test_cases = load_by_split("test")
    # Test split may be empty if golden set only has validation split
    assert all(case.split == "test" for case in test_cases)


def test_load_by_split_handles_none_split():
    """load_by_split can filter for cases with split=None."""
    none_cases = load_by_split(None)
    assert all(case.split is None for case in none_cases)


def test_load_golden_set_all_required_fields_present():
    """All test cases have required fields populated."""
    cases = load_golden_set()
    for case in cases:
        assert case.id
        assert case.base_query
        assert isinstance(case.expected_chunks, list)
        assert isinstance(case.paraphrases, list)
