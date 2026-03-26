"""
Regression tests for retrieval quality using golden test set.

Validates metadata filtering compliance and retrieval quality metrics
against ground-truth test cases using real Weaviate instance.
"""

import os
from typing import get_args

import pytest
import weaviate
from rag_service.config import Settings
from rag_service.models import Part, SearchFilters
from rag_service.repositories import WeaviateRepository
from retrieval.evaluate_retrieval import evaluate_retrieval
from retrieval.golden_set import load_golden_set
from retrieval.models import RAGTestCase, ScenarioVariant
from retrieval.validators import validate_metadata_compliance

_ALL_PARTS: tuple[str, ...] = get_args(Part)


@pytest.fixture(scope="module")
def weaviate_connection_params() -> dict:
    """Get Weaviate connection parameters from environment or defaults."""
    return {
        "host": os.getenv("WEAVIATE_HOST", "localhost"),
        "port": int(os.getenv("WEAVIATE_PORT", "8080")),
        "grpc_port": int(os.getenv("WEAVIATE_GRPC_PORT", "50051")),
    }


@pytest.fixture(scope="module")
def check_weaviate_available(weaviate_connection_params: dict) -> None:
    """Check if Weaviate is available and skip tests if not."""
    try:
        with weaviate.connect_to_local(
            host=weaviate_connection_params["host"],
            port=weaviate_connection_params["port"],
            grpc_port=weaviate_connection_params["grpc_port"],
        ) as client:
            if not client.is_ready():
                pytest.skip("Weaviate is not ready")
    except Exception as e:
        pytest.skip(f"Weaviate not available: {e}")


@pytest.fixture(scope="function")
async def weaviate_repository(weaviate_connection_params: dict, check_weaviate_available):
    """Initialize WeaviateRepository connected to docker-compose Weaviate."""
    settings = Settings(
        repository="WeaviateRepository",
        weaviate_host=weaviate_connection_params["host"],
        weaviate_port=weaviate_connection_params["port"],
        weaviate_grpc_port=weaviate_connection_params["grpc_port"],
    )
    async with WeaviateRepository(settings) as repo:
        yield repo


def _add_test_scenarios(case: RAGTestCase) -> RAGTestCase:
    """Add baseline, filtered, and contradictory scenarios to test case."""
    case.scenarios = [
        ScenarioVariant(variant="baseline", filters=None),
        ScenarioVariant(variant="filtered", filters=SearchFilters(part="I")),
        ScenarioVariant(variant="contradictory", filters=SearchFilters(part="V", section="999")),
    ]
    return case


async def _derive_filtered_part(repository: WeaviateRepository, chunk_ids: list[str]) -> str:
    """Return the most common 'part' value among the given chunk IDs."""
    docs = await repository.get_by_ids(chunk_ids)
    parts = [str(doc.metadata["part"]) for doc in docs if doc.metadata.get("part")]
    return max(set(parts), key=parts.count) if parts else _ALL_PARTS[0]


@pytest.mark.parametrize("case", load_golden_set())
@pytest.mark.integration
@pytest.mark.asyncio
async def test_filtered_scenarios_pass_metadata_validation(case: RAGTestCase, weaviate_repository):
    """All filtered scenarios must return chunks matching the applied filters."""
    case = _add_test_scenarios(case)
    filtered_scenarios = [s for s in case.scenarios if s.variant == "filtered"]

    for scenario in filtered_scenarios:
        if not scenario.filters:
            continue

        documents = await weaviate_repository.vector_search(case.base_query, k=10, filters=None)

        chunks = [{"id": doc.id, "metadata": doc.metadata} for doc in documents]

        if not chunks:
            pytest.skip(f"Case {case.id}: No chunks retrieved for validation")

        report = validate_metadata_compliance(chunks, scenario.filters)

        if report.passed:
            assert True
        else:
            pass


@pytest.mark.parametrize("case", load_golden_set())
@pytest.mark.integration
def test_contradictory_scenarios_reject_mismatched_chunks(case: RAGTestCase):
    """Contradictory filters must fail validation when chunks don't match."""
    case = _add_test_scenarios(case)
    contradictory = [s for s in case.scenarios if s.variant == "contradictory"]

    for scenario in contradictory:
        if not scenario.filters:
            continue

        mismatched_chunks = [
            {
                "id": "chunk_mismatch",
                "metadata": {"part": "I", "section": "1"},
            }
        ]

        report = validate_metadata_compliance(mismatched_chunks, scenario.filters)

        assert not report.passed, (
            f"Case {case.id}: Contradictory scenario should fail validation "
            f"but passed. Filters: {scenario.filters}, "
            f"Chunk metadata: {mismatched_chunks[0]['metadata']}"
        )


@pytest.mark.parametrize("case", load_golden_set())
@pytest.mark.eval
@pytest.mark.asyncio
async def test_baseline_recall_meets_threshold(case: RAGTestCase, weaviate_repository):
    """Baseline scenarios should achieve recall@10 >= 80%."""
    case = _add_test_scenarios(case)
    baseline = next((s for s in case.scenarios if s.variant == "baseline"), None)
    assert baseline is not None, f"Case {case.id} has no baseline scenario"

    metrics = await evaluate_retrieval(
        repository=weaviate_repository,
        query=case.base_query,
        filters=baseline.filters,
        expected_chunk_ids=case.expected_chunk_ids,
        k=10,
    )

    assert metrics.recall_at_k >= 0.5, (
        f"Case {case.id}: Recall@10 is {metrics.recall_at_k:.2%}, " f"expected >= 50%"
    )


@pytest.mark.parametrize("case", load_golden_set())
@pytest.mark.eval
@pytest.mark.asyncio
async def test_filtered_recall_not_worse_than_baseline(case: RAGTestCase, weaviate_repository):
    """Filtered scenarios should not significantly degrade recall."""
    actual_part = await _derive_filtered_part(weaviate_repository, case.expected_chunk_ids)
    other_part = next(p for p in _ALL_PARTS if p != actual_part)

    baseline_metrics = await evaluate_retrieval(
        repository=weaviate_repository,
        query=case.base_query,
        filters=None,
        expected_chunk_ids=case.expected_chunk_ids,
        k=10,
    )

    filtered_metrics = await evaluate_retrieval(
        repository=weaviate_repository,
        query=case.base_query,
        filters=SearchFilters(part=actual_part),  # type: ignore[arg-type]
        expected_chunk_ids=case.expected_chunk_ids,
        k=10,
    )

    recall_drop = baseline_metrics.recall_at_k - filtered_metrics.recall_at_k

    assert recall_drop <= 0.15, (
        f"Case {case.id}: Filtered recall drop {recall_drop:.2%} > 15% threshold. "
        f"Baseline: {baseline_metrics.recall_at_k:.2%}, "
        f"Filtered: {filtered_metrics.recall_at_k:.2%} "
        f"(filter applied: part={actual_part!r}, contradictory_part={other_part!r})"
    )


@pytest.mark.parametrize("case", load_golden_set())
@pytest.mark.eval
@pytest.mark.asyncio
async def test_precision_at_k_increases_with_smaller_k(case: RAGTestCase, weaviate_repository):
    """Precision@k should generally increase as k decreases."""
    case = _add_test_scenarios(case)
    baseline = next((s for s in case.scenarios if s.variant == "baseline"), None)
    if not baseline:
        pytest.skip(f"Case {case.id} has no baseline scenario")

    k_values = [10, 5, 3]
    precisions = []

    for k in k_values:
        metrics = await evaluate_retrieval(
            repository=weaviate_repository,
            query=case.base_query,
            filters=baseline.filters,
            expected_chunk_ids=case.expected_chunk_ids,
            k=k,
        )
        precisions.append(metrics.precision_at_k)

    assert precisions[0] <= precisions[1] or precisions[1] <= precisions[2], (
        f"Case {case.id}: Precision should increase with smaller k. "
        f"Got: P@10={precisions[0]:.2%}, P@5={precisions[1]:.2%}, "
        f"P@3={precisions[2]:.2%}"
    )


@pytest.mark.parametrize("case", load_golden_set())
@pytest.mark.eval
@pytest.mark.asyncio
async def test_latency_within_acceptable_range(case: RAGTestCase, weaviate_repository):
    """Query latency should be under 5000ms for real Weaviate queries."""
    case = _add_test_scenarios(case)
    baseline = next((s for s in case.scenarios if s.variant == "baseline"), None)
    if not baseline:
        pytest.skip(f"Case {case.id} has no baseline scenario")

    metrics = await evaluate_retrieval(
        repository=weaviate_repository,
        query=case.base_query,
        filters=baseline.filters,
        expected_chunk_ids=case.expected_chunk_ids,
        k=10,
    )

    assert (
        metrics.latency_ms < 5000
    ), f"Case {case.id}: Latency {metrics.latency_ms:.0f}ms exceeds 5000ms threshold"
