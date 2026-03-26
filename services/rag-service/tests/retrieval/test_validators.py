"""
Tests for metadata compliance validation.

Validates that retrieved chunks match SearchFilters constraints.
"""

import pytest
from rag_service.models import SearchFilters

from .validators import validate_metadata_compliance


def test_all_chunks_match_filters_returns_passed():
    retrieved_chunks = [
        {"id": "c1", "metadata": {"part": "I", "section": "2"}},
        {"id": "c2", "metadata": {"part": "I", "section": "2"}},
        {"id": "c3", "metadata": {"part": "I", "section": "2"}},
    ]
    filters = SearchFilters(part="I", section="2")

    report = validate_metadata_compliance(retrieved_chunks, filters)

    assert report.passed is True
    assert len(report.violations) == 0


def test_some_chunks_violate_filters_returns_violations():
    retrieved_chunks = [
        {"id": "c1", "metadata": {"part": "I", "section": "2"}},
        {"id": "c2", "metadata": {"part": "II", "section": "2"}},
        {"id": "c3", "metadata": {"part": "I", "section": "3"}},
    ]
    filters = SearchFilters(part="I", section="2")

    report = validate_metadata_compliance(retrieved_chunks, filters)

    assert report.passed is False
    assert len(report.violations) == 2
    assert any("c2" in v and "part" in v and "II" in v for v in report.violations)
    assert any("c3" in v and "section" in v and "3" in v for v in report.violations)


def test_all_chunks_violate_filters_returns_all_violations():
    retrieved_chunks = [
        {"id": "c1", "metadata": {"part": "II"}},
        {"id": "c2", "metadata": {"part": "III"}},
        {"id": "c3", "metadata": {"part": "IV"}},
    ]
    filters = SearchFilters(part="I")

    report = validate_metadata_compliance(retrieved_chunks, filters)

    assert report.passed is False
    assert len(report.violations) == 3


def test_empty_chunks_returns_passed():
    retrieved_chunks = []
    filters = SearchFilters(part="I", section="2")

    report = validate_metadata_compliance(retrieved_chunks, filters)

    assert report.passed is True
    assert len(report.violations) == 0


def test_none_filters_returns_passed():
    retrieved_chunks = [
        {"id": "c1", "metadata": {"part": "I"}},
        {"id": "c2", "metadata": {"part": "II"}},
    ]

    report = validate_metadata_compliance(retrieved_chunks, None)

    assert report.passed is True
    assert len(report.violations) == 0


def test_missing_metadata_field_in_chunk_is_violation():
    retrieved_chunks = [
        {"id": "c1", "metadata": {"part": "I"}},
        {"id": "c2", "metadata": {}},
    ]
    filters = SearchFilters(part="I")

    report = validate_metadata_compliance(retrieved_chunks, filters)

    assert report.passed is False
    assert len(report.violations) == 1
    assert "c2" in report.violations[0]


def test_chapter_filter_validation():
    retrieved_chunks = [
        {"id": "c1", "metadata": {"part": "I", "section": "1"}},
        {"id": "c2", "metadata": {"part": "I", "section": "2"}},
    ]
    filters = SearchFilters(part="I", section="1")

    report = validate_metadata_compliance(retrieved_chunks, filters)

    assert report.passed is False
    assert len(report.violations) == 1
    assert "c2" in report.violations[0]
    assert "section" in report.violations[0] and "2" in report.violations[0]


def test_subsection_filter_validation():
    retrieved_chunks = [
        {"id": "c1", "metadata": {"section": "2", "subsection": "2.3"}},
        {"id": "c2", "metadata": {"section": "2", "subsection": "2.4"}},
    ]
    filters = SearchFilters(section="2", subsection="2.3")

    report = validate_metadata_compliance(retrieved_chunks, filters)

    assert report.passed is False
    assert len(report.violations) == 1
    assert "c2" in report.violations[0]


def test_page_number_filter_validation():
    retrieved_chunks = [
        {"id": "c1", "metadata": {"page_number": 42}},
        {"id": "c2", "metadata": {"page_number": 43}},
    ]
    filters = SearchFilters(page_number=42)

    report = validate_metadata_compliance(retrieved_chunks, filters)

    assert report.passed is False
    assert len(report.violations) == 1
    assert "c2" in report.violations[0]


def test_multiple_filter_violations_in_single_chunk():
    retrieved_chunks = [
        {"id": "c1", "metadata": {"part": "II", "section": "4", "subsection": "4.1"}},
    ]
    filters = SearchFilters(part="I", section="3", subsection="3.1")

    report = validate_metadata_compliance(retrieved_chunks, filters)

    assert report.passed is False
    assert len(report.violations) == 1
    violation = report.violations[0]
    assert "c1" in violation
    assert "part" in violation and "II" in violation
    assert "section" in violation and "4" in violation
    assert "subsection" in violation and "4.1" in violation


@pytest.mark.parametrize(
    "chunks,filters,expected_passed",
    [
        (
            [{"id": "c1", "metadata": {"part": "I"}}],
            SearchFilters(part="I"),
            True,
        ),
        (
            [{"id": "c1", "metadata": {"part": "II"}}],
            SearchFilters(part="I"),
            False,
        ),
        (
            [{"id": "c1", "metadata": {"section": "5"}}],
            SearchFilters(section="5"),
            True,
        ),
        (
            [{"id": "c1", "metadata": {}}],
            SearchFilters(),
            True,
        ),
    ],
)
def test_single_field_validation_parametrized(chunks, filters, expected_passed):
    report = validate_metadata_compliance(chunks, filters)

    assert report.passed == expected_passed
