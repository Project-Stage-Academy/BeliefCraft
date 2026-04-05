"""
Golden set loader for RAG retrieval evaluation.

Reads golden_set.json and converts entries to RAGTestCase instances.
"""

import json
from pathlib import Path

try:
    from .models import RAGTestCase
except ImportError:
    from models import RAGTestCase


def load_golden_set(path: Path | str | None = None) -> list[RAGTestCase]:
    """Load golden set from JSON file.

    Args:
        path: Path to golden_set.json. If None, loads from default location
              (tests/retrieval/golden_set.json relative to this file).

    Returns:
        List of RAGTestCase instances.
    """
    path = Path(__file__).parent / "golden_set.json" if path is None else Path(path)

    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    cases: list[RAGTestCase] = []
    for entry in data:
        description = _generate_description(entry["question"])
        cases.append(
            RAGTestCase(
                id=entry["id"],
                description=description,
                base_query=entry["question"],
                paraphrases=entry.get("paraphrases", []),
                expected_chunk_ids=entry["expected_chunk_ids"],
                pdf_block_ids_map=entry.get("pdf_block_ids_map", {}),
                split=entry.get("split"),
            )
        )

    return cases


def _generate_description(question: str, max_length: int = 80) -> str:
    """Generate a short description from the question text.

    Args:
        question: Full question text.
        max_length: Maximum description length.

    Returns:
        Truncated question with ellipsis if needed.
    """
    if len(question) <= max_length:
        return question
    return question[: max_length - 3] + "..."


def load_by_split(split: str | None, path: Path | str | None = None) -> list[RAGTestCase]:
    """Load only test cases from a specific split.

    Args:
        split: Either "validation", "test", or None.
        path: Path to golden_set.json (optional).

    Returns:
        List of RAGTestCase instances matching the split.
    """
    all_cases = load_golden_set(path)
    return [case for case in all_cases if case.split == split]
