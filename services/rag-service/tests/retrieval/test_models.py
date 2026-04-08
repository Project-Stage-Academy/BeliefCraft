"""Tests for RAGTestCase Pydantic model."""

import pytest
from pydantic import ValidationError
from retrieval.models import ExpectedChunk, RAGTestCase


@pytest.fixture()
def minimal_test_case() -> RAGTestCase:
    """Minimal valid RAGTestCase."""
    return RAGTestCase(
        id="tc_test_001",
        description="A minimal test case",
        base_query="What is a POMDP?",
        expected_chunks=[ExpectedChunk(chunk_id="text_7a0afb97", pdf_block_ids=[])],
    )


def test_rag_test_case_creates_with_minimal_fields():
    """RAGTestCase can be created with only required fields."""
    tc = RAGTestCase(
        id="tc_001",
        base_query="What is belief state planning?",
        expected_chunks=[ExpectedChunk(chunk_id="text_abc123", pdf_block_ids=[])],
    )

    assert tc.id == "tc_001"
    assert tc.base_query == "What is belief state planning?"
    assert len(tc.expected_chunks) == 1
    assert tc.expected_chunks[0].chunk_id == "text_abc123"
    assert tc.description == ""
    assert tc.paraphrases == []
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
        expected_chunks=[
            ExpectedChunk(chunk_id="text_abc123", pdf_block_ids=["592:16", "592:17"]),
            ExpectedChunk(chunk_id="text_def456", pdf_block_ids=["593:0"]),
        ],
        split="validation",
    )

    assert tc.id == "tc_belief_update"
    assert tc.description == "Belief update via Bayes rule"
    assert tc.base_query == "How does Bayesian belief update work in a POMDP?"
    assert len(tc.paraphrases) == 2
    assert len(tc.expected_chunks) == 2
    assert tc.expected_chunks[0].chunk_id == "text_abc123"
    assert tc.expected_chunks[0].pdf_block_ids == ["592:16", "592:17"]
    assert tc.expected_chunks[1].chunk_id == "text_def456"
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
        expected_chunks=[ExpectedChunk(chunk_id="text_001", pdf_block_ids=[])],
        split=split_value,
    )

    assert tc.split == split_value


def test_rag_test_case_rejects_invalid_split():
    """RAGTestCase rejects invalid split values."""
    with pytest.raises(ValidationError):
        RAGTestCase(
            id="tc_x",
            base_query="query",
            expected_chunks=[ExpectedChunk(chunk_id="text_001", pdf_block_ids=[])],
            split="invalid",  # type: ignore[arg-type]
        )


def test_rag_test_case_empty_expected_chunks_is_valid():
    """RAGTestCase allows empty expected_chunks list."""
    tc = RAGTestCase(
        id="tc_x",
        base_query="query",
        expected_chunks=[],
    )

    assert tc.expected_chunks == []


def test_rag_test_case_empty_paraphrases_is_default():
    """Paraphrases defaults to empty list."""
    tc = RAGTestCase(
        id="tc_x",
        base_query="query",
        expected_chunks=[ExpectedChunk(chunk_id="text_001", pdf_block_ids=[])],
    )

    assert tc.paraphrases == []


def test_rag_test_case_expected_chunk_with_pdf_blocks():
    """Expected chunks can include pdf_block_ids for traceability."""
    tc = RAGTestCase(
        id="tc_x",
        base_query="query",
        expected_chunks=[ExpectedChunk(chunk_id="text_001", pdf_block_ids=["23:0", "23:1"])],
    )

    assert tc.expected_chunks[0].pdf_block_ids == ["23:0", "23:1"]


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
        expected_chunks=[ExpectedChunk(chunk_id="text_001", pdf_block_ids=[])],
        paraphrases=paraphrases,
    )

    assert len(tc.paraphrases) == 3
    assert tc.paraphrases == paraphrases


def test_rag_test_case_expected_chunks_structure():
    """Expected chunks correctly store chunk_id and pdf_block_ids."""
    tc = RAGTestCase(
        id="tc_x",
        base_query="query",
        expected_chunks=[
            ExpectedChunk(chunk_id="text_7a0afb97", pdf_block_ids=["592:16", "592:17", "592:18"]),
            ExpectedChunk(chunk_id="text_abc123", pdf_block_ids=["88:11"]),
            ExpectedChunk(chunk_id="algorithm_xyz", pdf_block_ids=["105:3", "105:4"]),
        ],
    )

    assert len(tc.expected_chunks) == 3
    assert tc.expected_chunks[0].chunk_id == "text_7a0afb97"
    assert tc.expected_chunks[0].pdf_block_ids == ["592:16", "592:17", "592:18"]
    assert tc.expected_chunks[2].chunk_id == "algorithm_xyz"


def test_rag_test_case_description_can_be_empty_string():
    """Description can be explicitly set to empty string."""
    tc = RAGTestCase(
        id="tc_x",
        description="",
        base_query="query",
        expected_chunks=[ExpectedChunk(chunk_id="text_001", pdf_block_ids=[])],
    )

    assert tc.description == ""


def test_rag_test_case_instances_are_independent():
    """Multiple instances don't share mutable defaults."""
    tc1 = RAGTestCase(
        id="tc_1",
        base_query="query1",
        expected_chunks=[ExpectedChunk(chunk_id="text_001", pdf_block_ids=[])],
    )
    tc2 = RAGTestCase(
        id="tc_2",
        base_query="query2",
        expected_chunks=[ExpectedChunk(chunk_id="text_002", pdf_block_ids=[])],
    )

    tc1.paraphrases.append("paraphrase1")
    tc1.expected_chunks[0].pdf_block_ids.append("1:0")

    assert tc2.paraphrases == []
    assert tc2.expected_chunks[0].pdf_block_ids == []


def test_rag_test_case_validates_chunk_id_format():
    """Expected chunk IDs must be strings (stable parser IDs like 'text_7a0afb97')."""
    tc = RAGTestCase(
        id="tc_x",
        base_query="query",
        expected_chunks=[
            ExpectedChunk(chunk_id="text_7a0afb97", pdf_block_ids=[]),
            ExpectedChunk(chunk_id="algorithm_abc123", pdf_block_ids=[]),
            ExpectedChunk(chunk_id="exercise_def456", pdf_block_ids=[]),
        ],
    )

    assert all(isinstance(chunk.chunk_id, str) for chunk in tc.expected_chunks)
    assert any(chunk.chunk_id == "text_7a0afb97" for chunk in tc.expected_chunks)
