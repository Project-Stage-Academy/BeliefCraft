"""
Metadata compliance validation for retrieved chunks.

Validates that retrieved chunks satisfy SearchFilters constraints without LLM.
"""

import logging
from typing import Any

from pydantic import BaseModel
from rag_service.models import SearchFilters

logger = logging.getLogger(__name__)


class ValidationReport(BaseModel):
    """Report of metadata compliance validation.

    Args:
        passed: True if all retrieved chunks satisfy the active filters.
        violations: List of human-readable violation messages for debugging.
    """

    passed: bool
    violations: list[str]


def _is_match(actual: Any, expected: Any) -> bool:
    """Perform a type-flexible comparison between actual and expected metadata values.

    Handles common edge cases like integer-to-float comparison (5 vs 5.0)
    and string normalization (stripping whitespace).

    Args:
        actual: The value found in the retrieved document's metadata.
        expected: The value defined in the SearchFilters.

    Returns:
        True if values are considered equal, False otherwise.
    """
    if actual is None or expected is None:
        return actual == expected

    if isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
        return float(actual) == float(expected)

    return str(actual).strip() == str(expected).strip()


def validate_metadata_compliance(
    retrieved_chunks: list[dict[str, Any]], filters: SearchFilters | None
) -> ValidationReport:
    """Validate that all retrieved chunks strictly match the SearchFilters constraints.

    This function iterates through every document returned by the search and
    checks if the metadata fields (part, section, etc.) match the filter values.
    It is used in integration tests to detect "filter leaks" or index issues.

    Args:
        retrieved_chunks: List of chunk dictionaries containing 'id' and 'metadata'.
        filters: The SearchFilters object applied to the query.

    Returns:
        ValidationReport containing the pass/fail status and violation details.
    """
    if filters is None or not retrieved_chunks:
        return ValidationReport(passed=True, violations=[])

    logger.debug("Retrieved chunks: %s", retrieved_chunks)
    logger.debug("Filters applied: %s", filters)

    violations: list[str] = []

    filter_map = {
        "part": filters.part,
        "section": filters.section,
        "subsection": filters.subsection,
        "subsubsection": filters.subsubsection,
        "page_number": filters.page_number,
    }

    active_filters = {k: v for k, v in filter_map.items() if v is not None}

    for chunk in retrieved_chunks:
        chunk_id = chunk.get("id", "unknown_id")
        metadata = chunk.get("metadata", {})

        chunk_violations = []
        for field, expected_value in active_filters.items():
            actual_value = metadata.get(field)

            if not _is_match(actual_value, expected_value):
                chunk_violations.append(
                    f"{field}: actual '{actual_value}' != expected '{expected_value}'"
                )

        if chunk_violations:
            violation_msg = f"Document {chunk_id} violated: {'; '.join(chunk_violations)}"
            violations.append(violation_msg)

    if violations:
        logger.debug("Validation violations: %s", violations)

    return ValidationReport(passed=len(violations) == 0, violations=violations)
