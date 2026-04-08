"""
Pydantic schemas for RAG retrieval test cases.

Defines the canonical representation of a single retrieval test case
used by the evaluation suite.
"""

from typing import Literal

from pydantic import BaseModel, Field


class ExpectedChunk(BaseModel):
    """Expected chunk with traceability to PDF blocks.

    Args:
        chunk_id: Stable chunk identifier from JSON parser (e.g. ``text_7a0afb97``).
        pdf_block_ids: Corresponding PDF block IDs for traceability
            (e.g. ``["23:0", "23:1"]``).
    """

    chunk_id: str
    pdf_block_ids: list[str] = Field(default_factory=list)


class RAGTestCase(BaseModel):
    """Canonical representation of a single retrieval test case.

    Args:
        id: Unique stable identifier, e.g. ``tc_001``.
        description: Human-readable one-liner for documentation.
        base_query: Text question submitted to the retrieval pipeline.
        paraphrases: Alternative phrasings of ``base_query`` with identical
            ``expected_chunks``. Each paraphrase is evaluated as an
            independent query to test semantic search robustness.
        expected_chunks: Ground-truth chunks that MUST appear in results.
            Each chunk includes stable chunk_id and corresponding pdf_block_ids
            for traceability.
        split: Dataset split assignment (``validation`` or ``test``).
    """

    id: str
    description: str = ""
    base_query: str
    paraphrases: list[str] = Field(default_factory=list)
    expected_chunks: list[ExpectedChunk]
    split: Literal["validation", "test"] | None = None
