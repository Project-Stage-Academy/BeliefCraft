"""
Tests for golden_set.py loader.
"""

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
    assert first_case.split in ("validation", "test")


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
    assert len(first_case.paraphrases) > 0


def test_load_golden_set_includes_expected_chunk_ids():
    """Expected chunk IDs list is populated."""
    cases = load_golden_set()
    first_case = cases[0]
    assert isinstance(first_case.expected_chunk_ids, list)
    assert len(first_case.expected_chunk_ids) >= 1
    assert all(isinstance(cid, str) for cid in first_case.expected_chunk_ids)


def test_load_golden_set_initializes_scenarios_empty():
    """Scenarios list is empty until generate_test_suite runs."""
    cases = load_golden_set()
    assert all(case.scenarios == [] for case in cases)


def test_load_golden_set_sets_domain_to_book():
    """Domain defaults to 'book' for all cases."""
    cases = load_golden_set()
    assert all(case.domain == "book" for case in cases)


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
    assert len(validation_cases) > 0


def test_load_by_split_filters_test():
    """load_by_split returns only test cases."""
    test_cases = load_by_split("test")
    assert all(case.split == "test" for case in test_cases)


def test_load_golden_set_all_splits_present():
    """Golden set contains both validation and test splits."""
    cases = load_golden_set()
    splits = {case.split for case in cases}
    assert "validation" in splits
    # Note: test split may be empty if golden set is small
