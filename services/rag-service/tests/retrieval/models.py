"""
Pydantic schemas for RAG retrieval test cases.

Defines the canonical representation of a single retrieval test case
and its scenario variants used by the regression and evaluation suites.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field
from rag_service.models import EntityType, SearchFilters


class ScenarioVariant(BaseModel):
    """A single test scenario applied on top of a RAGTestCase.

    Three canonical variants exist per test case:
    - baseline: pure semantic search, no filters.
    - filtered: correct metadata filter matching the expected chunk.
    - contradictory: mismatched filter that must yield an empty result.

    Args:
        variant: Which scenario this represents.
        filters: Optional metadata filter to apply to the query.
        boost_params: Reserved for future relevance boosting parameters.
        traverse_types: Entity types for in-query graph expansion via
            ``search_knowledge_base`` ``traverse_types`` parameter.
        expect_empty: When ``True``, an empty result set is the pass condition.
        latency_budget_ms: Maximum acceptable wall-clock response time in ms.
    """

    variant: Literal["baseline", "filtered", "contradictory"]
    filters: SearchFilters | None = None
    boost_params: dict[str, Any] | None = None
    traverse_types: list[EntityType] | None = None
    expect_empty: bool = False
    latency_budget_ms: int = Field(default=1000, gt=0)


class RAGTestCase(BaseModel):
    """Canonical representation of a single retrieval test case.

    Args:
        id: Unique stable identifier, e.g. ``tc_pomdp_belief_update``.
        description: Human-readable one-liner for documentation.
        base_query: Text question submitted to the retrieval pipeline.
        paraphrases: Alternative phrasings of ``base_query`` with identical
            ``expected_chunk_ids``. Each paraphrase is evaluated as an
            independent query to test semantic search robustness.
        expected_chunk_ids: Ground-truth Weaviate UUIDs that MUST appear
            in results for the test to pass. May span multiple chunks from
            different corpus groups.
        scenarios: Scenario variants generated from this test case.
        expected_metadata: Key-value pairs every returned chunk must satisfy.
        domain: Selects the correct test runner for this case.
        split: Dataset split assignment. ``None`` until the golden set reaches
            \u226540 entries and the 80/20 split is locked in.
    """

    id: str
    description: str
    base_query: str
    paraphrases: list[str] = Field(default_factory=list)
    expected_chunk_ids: list[str]
    scenarios: list[ScenarioVariant]
    expected_metadata: dict[str, Any] = Field(default_factory=dict)
    domain: Literal["book", "warehouse", "cross_domain"] = "book"
    split: Literal["validation", "test"] | None = None
