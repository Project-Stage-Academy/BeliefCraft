"""
Tests for generate_test_suite.py
"""

from .generate_test_suite import (
    generate_baseline_variant,
    generate_contradictory_variant,
    generate_filtered_variants,
    generate_scenarios_for_case,
)
from .models import RAGTestCase


def test_generate_baseline_variant_has_no_filters():
    """Baseline variant has no filters set."""
    variant = generate_baseline_variant()
    assert variant.variant == "baseline"
    assert variant.filters is None
    assert variant.expect_empty is False


def test_generate_baseline_variant_has_default_latency_budget():
    """Baseline variant has 1000ms latency budget."""
    variant = generate_baseline_variant()
    assert variant.latency_budget_ms == 1000


def test_generate_filtered_variants_creates_one_per_unique_metadata():
    """Filtered variants are created for each unique metadata combination."""
    metadata_map = {
        "uuid1": {"part": "I", "section_number": "2"},
        "uuid2": {"part": "I", "section_number": "2"},  # Duplicate
        "uuid3": {"part": "II", "section_number": "3"},
    }

    variants = generate_filtered_variants(metadata_map)

    assert len(variants) == 2  # Two unique combinations
    assert all(v.variant == "filtered" for v in variants)
    assert all(v.expect_empty is False for v in variants)


def test_generate_filtered_variants_preserves_metadata_fields():
    """Filtered variant filters match chunk metadata."""
    metadata_map = {
        "uuid1": {
            "part": "III",
            "section_number": "5",
            "subsection_number": "5.2",
            "page": 42,
        }
    }

    variants = generate_filtered_variants(metadata_map)

    assert len(variants) == 1
    filters = variants[0].filters
    assert filters is not None
    assert filters.part == "III"
    assert filters.section == "5"
    assert filters.subsection == "5.2"
    assert filters.page_number == 42


def test_generate_filtered_variants_handles_partial_metadata():
    """Filtered variants work with incomplete metadata."""
    metadata_map = {
        "uuid1": {"part": "I"},  # Only part, no section
        "uuid2": {"section_number": "3"},  # Only section, no part
    }

    variants = generate_filtered_variants(metadata_map)

    assert len(variants) == 2
    assert any(v.filters.part == "I" for v in variants)
    assert any(v.filters.section == "3" for v in variants)


def test_generate_contradictory_variant_has_mismatched_part():
    """Contradictory variant part does not match any chunk."""
    metadata_map = {
        "uuid1": {"part": "I"},
        "uuid2": {"part": "II"},
    }

    variant = generate_contradictory_variant(metadata_map)

    assert variant.variant == "contradictory"
    assert variant.expect_empty is True
    assert variant.filters is not None
    assert variant.filters.part not in ("I", "II")


def test_generate_contradictory_variant_falls_back_to_part_v():
    """Contradictory variant defaults to Part V if all parts are taken."""
    metadata_map = {
        f"uuid{i}": {"part": part} for i, part in enumerate(["I", "II", "III", "IV", "Appendices"])
    }

    variant = generate_contradictory_variant(metadata_map)

    assert variant.filters.part == "V"


def test_generate_scenarios_for_case_includes_baseline():
    """Generated scenarios include baseline variant."""
    case = RAGTestCase(
        id="tc_001",
        description="Test case",
        base_query="Test query",
        expected_chunk_ids=["uuid1"],
        scenarios=[],
        domain="book",
    )

    metadata_map = {"uuid1": {"part": "I"}}
    scenarios = generate_scenarios_for_case(case, metadata_map)

    assert any(s.variant == "baseline" for s in scenarios)


def test_generate_scenarios_for_case_includes_filtered():
    """Generated scenarios include filtered variants."""
    case = RAGTestCase(
        id="tc_001",
        description="Test case",
        base_query="Test query",
        expected_chunk_ids=["uuid1", "uuid2"],
        scenarios=[],
        domain="book",
    )

    metadata_map = {
        "uuid1": {"part": "I", "section_number": "2"},
        "uuid2": {"part": "II", "section_number": "3"},
    }

    scenarios = generate_scenarios_for_case(case, metadata_map)

    filtered_scenarios = [s for s in scenarios if s.variant == "filtered"]
    assert len(filtered_scenarios) >= 1


def test_generate_scenarios_for_case_includes_contradictory():
    """Generated scenarios include contradictory variant."""
    case = RAGTestCase(
        id="tc_001",
        description="Test case",
        base_query="Test query",
        expected_chunk_ids=["uuid1"],
        scenarios=[],
        domain="book",
    )

    metadata_map = {"uuid1": {"part": "I"}}
    scenarios = generate_scenarios_for_case(case, metadata_map)

    assert any(s.variant == "contradictory" for s in scenarios)


def test_generate_scenarios_for_case_total_count():
    """Generated scenarios = 1 baseline + N filtered + 1 contradictory."""
    case = RAGTestCase(
        id="tc_001",
        description="Test case",
        base_query="Test query",
        expected_chunk_ids=["uuid1", "uuid2"],
        scenarios=[],
        domain="book",
    )

    metadata_map = {
        "uuid1": {"part": "I", "section_number": "2"},
        "uuid2": {"part": "II", "section_number": "3"},
    }

    scenarios = generate_scenarios_for_case(case, metadata_map)

    baseline_count = sum(1 for s in scenarios if s.variant == "baseline")
    filtered_count = sum(1 for s in scenarios if s.variant == "filtered")
    contradictory_count = sum(1 for s in scenarios if s.variant == "contradictory")

    assert baseline_count == 1
    assert filtered_count >= 1
    assert contradictory_count == 1
