"""
Pydantic schemas for RAG retrieval test cases.

Defines the canonical representation of a single retrieval test case
used by the evaluation suite.
"""

from typing import Literal

from pydantic import BaseModel, Field


class RAGTestCase(BaseModel):
    """Canonical representation of a single retrieval test case.

    Args:
        id: Unique stable identifier, e.g. ``tc_001``.
        description: Human-readable one-liner for documentation.
        base_query: Text question submitted to the retrieval pipeline.
        paraphrases: Alternative phrasings of ``base_query`` with identical
            ``expected_chunk_ids``. Each paraphrase is evaluated as an
            independent query to test semantic search robustness.
        expected_chunk_ids: Ground-truth chunk_ids (from JSON parser, e.g.
            ``text_7a0afb97``) that MUST appear in results for the test to pass.
            These are stable identifiers, not Weaviate UUIDs.
        pdf_block_ids_map: Mapping from chunk_id to corresponding pdf_block_ids
            (e.g. ``{"text_7a0afb97": ["23:0", "23:1"]}``). Used for traceability
            to original PDF blocks.
        split: Dataset split assignment (``validation`` or ``test``).
    """

    id: str
    description: str = ""
    base_query: str
    paraphrases: list[str] = Field(default_factory=list)
    expected_chunk_ids: list[str]
    pdf_block_ids_map: dict[str, list[str]] = Field(default_factory=dict)
    split: Literal["validation", "test"] | None = None
