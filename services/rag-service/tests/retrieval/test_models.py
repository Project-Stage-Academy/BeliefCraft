"""Tests for RAGTestCase Pydantic model."""

import pytest
from pydantic import ValidationError
from retrieval.models import RAGTestCase


@pytest.fixture()
def minimal_test_case() -> RAGTestCase:
    """Minimal valid RAGTestCase."""
    return RAGTestCase(
        id="tc_test_001",
        description="A minimal test case",
        base_query="What is a POMDP?",
        expected_chunk_ids=["text_7a0afb97"],
    )


def test_rag_test_case_creates_with_minimal_fields():
    """RAGTestCase can be created with only required fields."""
    tc = RAGTestCase(
        id="tc_001",
        base_query="What is belief state planning?",
        expected_chunk_ids=["text_abc123"],
    )

    assert tc.id == "tc_001"
    assert tc.base_query == "What is belief state planning?"
    assert tc.expected_chunk_ids == ["text_abc123"]
    assert tc.description == ""
    assert tc.paraphrases == []
    assert tc.pdf_block_ids_map == {}
    assert tc.split is None


def test_rag_test_case_creates_with_all_fields():
    """RAGTestCase stores all optional fields correctly."""
    tc = RAGTestCase(
        id="tc_belief_update",
        description="Belief update via Bayes rule",
        base_query="How does Bayesian belief update work in a POMDP?",
        paraphrases=[
            "Explain belief updates in POMDPs",
            "How to update beliefs in partially observable environments?",
        ],
        expected_chunk_ids=["text_abc123", "text_def456"],
        pdf_block_ids_map={
            "text_abc123": ["592:16", "592:17"],
            "text_def456": ["593:0"],
        },
        split="validation",
    )

    assert tc.id == "tc_belief_update"
    assert tc.description == "Belief update via Bayes rule"
    assert tc.base_query == "How does Bayesian belief update work in a POMDP?"
    assert len(tc.paraphrases) == 2
    assert len(tc.expected_chunk_ids) == 2
    assert "text_abc123" in tc.pdf_block_ids_map
    assert tc.split == "validation"


@pytest.mark.parametrize(
    "split_value",
    ["validation", "test", None],
)
def test_rag_test_case_accepts_valid_split_values(split_value):
    """RAGTestCase accepts validation, test, or None for split field."""
    tc = RAGTestCase(
        id="tc_x",
        base_query="query",
        expected_chunk_ids=["text_001"],
        split=split_value,
    )

    assert tc.split == split_value


def test_rag_test_case_rejects_invalid_split():
    """RAGTestCase rejects invalid split values."""
    with pytest.raises(ValidationError):
        RAGTestCase(
            id="tc_x",
            base_query="query",
            expected_chunk_ids=["text_001"],
            split="invalid",  # type: ignore[arg-type]
        )


def test_rag_test_case_empty_expected_chunk_ids_is_valid():
    """RAGTestCase allows empty expected_chunk_ids list."""
    tc = RAGTestCase(
        id="tc_x",
        base_query="query",
        expected_chunk_ids=[],
    )

    assert tc.expected_chunk_ids == []


def test_rag_test_case_empty_paraphrases_is_default():
    """Paraphrases defaults to empty list."""
    tc = RAGTestCase(
        id="tc_x",
        base_query="query",
        expected_chunk_ids=["text_001"],
    )

    assert tc.paraphrases == []


def test_rag_test_case_pdf_block_ids_map_defaults_to_empty_dict():
    """pdf_block_ids_map defaults to empty dict."""
    tc = RAGTestCase(
        id="tc_x",
        base_query="query",
        expected_chunk_ids=["text_001"],
    )

    assert tc.pdf_block_ids_map == {}


def test_rag_test_case_stores_multiple_paraphrases():
    """RAGTestCase stores list of paraphrases correctly."""
    paraphrases = [
        "First paraphrase",
        "Second paraphrase",
        "Third paraphrase",
    ]

    tc = RAGTestCase(
        id="tc_x",
        base_query="query",
        expected_chunk_ids=["text_001"],
        paraphrases=paraphrases,
    )

    assert len(tc.paraphrases) == 3
    assert tc.paraphrases == paraphrases


def test_rag_test_case_pdf_block_ids_map_structure():
    """pdf_block_ids_map correctly maps chunk_id to list of pdf_block_ids."""
    pdf_map = {
        "text_7a0afb97": ["592:16", "592:17", "592:18"],
        "text_abc123": ["88:11"],
        "algorithm_xyz": ["105:3", "105:4"],
    }

    tc = RAGTestCase(
        id="tc_x",
        base_query="query",
        expected_chunk_ids=["text_7a0afb97", "text_abc123"],
        pdf_block_ids_map=pdf_map,
    )

    assert tc.pdf_block_ids_map == pdf_map
    assert tc.pdf_block_ids_map["text_7a0afb97"] == ["592:16", "592:17", "592:18"]


def test_rag_test_case_description_can_be_empty_string():
    """Description can be explicitly set to empty string."""
    tc = RAGTestCase(
        id="tc_x",
        description="",
        base_query="query",
        expected_chunk_ids=["text_001"],
    )

    assert tc.description == ""


def test_rag_test_case_instances_are_independent():
    """Multiple instances don't share mutable defaults."""
    tc1 = RAGTestCase(
        id="tc_1",
        base_query="query1",
        expected_chunk_ids=["text_001"],
    )
    tc2 = RAGTestCase(
        id="tc_2",
        base_query="query2",
        expected_chunk_ids=["text_002"],
    )

    tc1.paraphrases.append("paraphrase1")
    tc1.pdf_block_ids_map["text_001"] = ["1:0"]

    assert tc2.paraphrases == []
    assert tc2.pdf_block_ids_map == {}


def test_rag_test_case_validates_chunk_id_format():
    """Expected chunk IDs must be strings (stable parser IDs like 'text_7a0afb97')."""
    tc = RAGTestCase(
        id="tc_x",
        base_query="query",
        expected_chunk_ids=["text_7a0afb97", "algorithm_abc123", "exercise_def456"],
    )

    assert all(isinstance(cid, str) for cid in tc.expected_chunk_ids)
    assert "text_7a0afb97" in tc.expected_chunk_ids
