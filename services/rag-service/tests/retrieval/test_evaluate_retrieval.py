"""
Tests for retrieval evaluation metrics.

Verifies recall@k, precision@k calculation, latency tracking, and cache behavior.
"""

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from rag_service.models import Document, SearchFilters
from retrieval.evaluate_retrieval import (
    RetrievalMetrics,
    compute_metrics,
    evaluate_retrieval,
)


@pytest.fixture
def mock_repository() -> AsyncMock:
    """Mock repository that returns controlled search results."""
    repo = AsyncMock()
    repo.vector_search = AsyncMock()
    return repo


@pytest.fixture
def sample_documents() -> list[Document]:
    """Sample documents for testing."""
    return [
        Document(
            id="uuid-001",
            content="POMDP belief update",
            cosine_similarity=0.95,
            metadata={"chunk_type": "text", "page": 10},
        ),
        Document(
            id="uuid-002",
            content="Bayesian filtering",
            cosine_similarity=0.88,
            metadata={"chunk_type": "text", "page": 15},
        ),
        Document(
            id="uuid-003",
            content="Sequential decision making",
            cosine_similarity=0.82,
            metadata={"chunk_type": "text", "page": 20},
        ),
    ]


@pytest.fixture(autouse=True)
def clean_eval_cache(tmp_path: Path, monkeypatch) -> Path:
    """Clean eval cache before each test."""
    cache_dir = tmp_path / ".eval_cache"
    cache_dir.mkdir()
    monkeypatch.setattr("retrieval.evaluate_retrieval.EVAL_CACHE_DIR", cache_dir)
    return cache_dir


@pytest.fixture
def eval_cache_dir(tmp_path: Path) -> Path:
    """Create temporary eval cache directory."""
    cache_dir = tmp_path / ".eval_cache"
    cache_dir.mkdir(exist_ok=True)
    return cache_dir


# ---------------------------------------------------------------------------
# compute_metrics — happy paths
# ---------------------------------------------------------------------------


def test_compute_metrics_calculates_perfect_recall() -> None:
    retrieved_ids = ["uuid-001", "uuid-002", "uuid-003"]
    expected_ids = ["uuid-001", "uuid-002", "uuid-003"]
    k = 3

    result = compute_metrics(retrieved_ids, expected_ids, k)

    assert result.recall_at_k == 1.0
    assert result.precision_at_k == 1.0
    assert result.k == 3


def test_compute_metrics_calculates_partial_recall() -> None:
    retrieved_ids = ["uuid-001", "uuid-002", "uuid-999"]
    expected_ids = ["uuid-001", "uuid-002", "uuid-003"]
    k = 3

    result = compute_metrics(retrieved_ids, expected_ids, k)

    assert result.recall_at_k == pytest.approx(0.667, abs=0.01)
    assert result.precision_at_k == pytest.approx(0.667, abs=0.01)


def test_compute_metrics_calculates_zero_recall() -> None:
    retrieved_ids = ["uuid-999", "uuid-888", "uuid-777"]
    expected_ids = ["uuid-001", "uuid-002", "uuid-003"]
    k = 3

    result = compute_metrics(retrieved_ids, expected_ids, k)

    assert result.recall_at_k == 0.0
    assert result.precision_at_k == 0.0


def test_compute_metrics_handles_k_smaller_than_expected() -> None:
    retrieved_ids = ["uuid-001", "uuid-002"]
    expected_ids = ["uuid-001", "uuid-002", "uuid-003", "uuid-004"]
    k = 2

    result = compute_metrics(retrieved_ids, expected_ids, k)

    assert result.recall_at_k == 0.5
    assert result.precision_at_k == 1.0


def test_compute_metrics_handles_k_larger_than_retrieved() -> None:
    retrieved_ids = ["uuid-001", "uuid-002"]
    expected_ids = ["uuid-001", "uuid-002"]
    k = 10

    result = compute_metrics(retrieved_ids, expected_ids, k)

    assert result.recall_at_k == 1.0
    assert result.precision_at_k == 0.2


def test_compute_metrics_stores_k_value() -> None:
    retrieved_ids = ["uuid-001"]
    expected_ids = ["uuid-001"]
    k = 5

    result = compute_metrics(retrieved_ids, expected_ids, k)

    assert result.k == 5


def test_compute_metrics_handles_empty_expected_list() -> None:
    retrieved_ids = ["uuid-001", "uuid-002"]
    expected_ids = []
    k = 2

    result = compute_metrics(retrieved_ids, expected_ids, k)

    assert result.recall_at_k == 0.0
    assert result.precision_at_k == 0.0


def test_compute_metrics_handles_empty_retrieved_list() -> None:
    retrieved_ids = []
    expected_ids = ["uuid-001", "uuid-002"]
    k = 5

    result = compute_metrics(retrieved_ids, expected_ids, k)

    assert result.recall_at_k == 0.0
    assert result.precision_at_k == 0.0


# ---------------------------------------------------------------------------
# compute_metrics — edge cases
# ---------------------------------------------------------------------------


def test_compute_metrics_handles_duplicate_ids_in_retrieved() -> None:
    retrieved_ids = ["uuid-001", "uuid-001", "uuid-002"]
    expected_ids = ["uuid-001", "uuid-002", "uuid-003"]
    k = 3

    result = compute_metrics(retrieved_ids, expected_ids, k)

    assert result.recall_at_k == pytest.approx(0.667, abs=0.01)
    assert result.precision_at_k == pytest.approx(0.667, abs=0.01)


def test_compute_metrics_handles_duplicate_ids_in_expected() -> None:
    retrieved_ids = ["uuid-001", "uuid-002", "uuid-003"]
    expected_ids = ["uuid-001", "uuid-001", "uuid-002"]
    k = 3

    result = compute_metrics(retrieved_ids, expected_ids, k)

    assert result.recall_at_k == 1.0
    assert result.precision_at_k == pytest.approx(0.667, abs=0.01)


# ---------------------------------------------------------------------------
# RetrievalMetrics model
# ---------------------------------------------------------------------------


def test_retrieval_metrics_stores_all_required_fields() -> None:
    metrics = RetrievalMetrics(
        recall_at_k=0.8,
        precision_at_k=0.75,
        mrr_at_k=0.7,
        latency_ms=245.5,
        k=10,
        num_retrieved=10,
        num_expected=5,
    )

    assert metrics.recall_at_k == 0.8
    assert metrics.precision_at_k == 0.75
    assert metrics.mrr_at_k == 0.7
    assert metrics.latency_ms == 245.5
    assert metrics.k == 10
    assert metrics.num_retrieved == 10
    assert metrics.num_expected == 5


def test_retrieval_metrics_serializes_to_dict() -> None:
    metrics = RetrievalMetrics(
        recall_at_k=0.9,
        precision_at_k=0.85,
        mrr_at_k=0.8,
        latency_ms=150.0,
        k=5,
        num_retrieved=5,
        num_expected=4,
    )

    result = metrics.model_dump()

    assert result["recall_at_k"] == 0.9
    assert result["precision_at_k"] == 0.85
    assert result["mrr_at_k"] == 0.8
    assert result["latency_ms"] == 150.0
    assert result["k"] == 5


# ---------------------------------------------------------------------------
# evaluate_retrieval — happy paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_evaluate_retrieval_returns_metrics_for_perfect_match(
    mock_repository: AsyncMock, sample_documents: list[Document]
) -> None:
    mock_repository.vector_search.return_value = sample_documents
    query = "What is a POMDP?"
    expected_ids = ["uuid-001", "uuid-002", "uuid-003"]
    k = 3

    result = await evaluate_retrieval(mock_repository, query, None, expected_ids, k)

    assert result.recall_at_k == 1.0
    assert result.precision_at_k == 1.0
    assert result.latency_ms > 0
    assert result.k == 3
    assert result.num_retrieved == 3
    assert result.num_expected == 3


@pytest.mark.asyncio
async def test_evaluate_retrieval_passes_query_to_repository(
    mock_repository: AsyncMock, sample_documents: list[Document]
) -> None:
    mock_repository.vector_search.return_value = sample_documents
    query = "Explain belief updates"
    expected_ids = ["uuid-001"]

    await evaluate_retrieval(mock_repository, query, None, expected_ids, k=5)

    mock_repository.vector_search.assert_called_once_with(query, 5, None)


@pytest.mark.asyncio
async def test_evaluate_retrieval_passes_filters_to_repository(
    mock_repository: AsyncMock, sample_documents: list[Document]
) -> None:
    mock_repository.vector_search.return_value = sample_documents
    filters = SearchFilters(part="I", section="2")
    query = "Sequential decisions"
    expected_ids = ["uuid-001"]

    await evaluate_retrieval(mock_repository, query, filters, expected_ids, k=3)

    mock_repository.vector_search.assert_called_once()
    call_args = mock_repository.vector_search.call_args
    assert call_args[0][0] == query
    assert call_args[0][1] == 3
    assert call_args[0][2] is not None


@pytest.mark.asyncio
async def test_evaluate_retrieval_measures_latency(
    mock_repository: AsyncMock, sample_documents: list[Document]
) -> None:
    async def slow_search(*args, **kwargs):
        import asyncio

        await asyncio.sleep(0.01)
        return sample_documents

    mock_repository.vector_search = slow_search
    query = "Test latency"
    expected_ids = ["uuid-001"]

    result = await evaluate_retrieval(mock_repository, query, None, expected_ids, k=5)

    assert result.latency_ms >= 10.0


@pytest.mark.asyncio
async def test_evaluate_retrieval_handles_partial_match(
    mock_repository: AsyncMock, sample_documents: list[Document]
) -> None:
    mock_repository.vector_search.return_value = sample_documents[:2]
    query = "POMDP"
    expected_ids = ["uuid-001", "uuid-002", "uuid-999"]
    k = 2

    result = await evaluate_retrieval(mock_repository, query, None, expected_ids, k)

    assert result.recall_at_k == pytest.approx(0.667, abs=0.01)
    assert result.precision_at_k == 1.0
    assert result.num_retrieved == 2
    assert result.num_expected == 3


@pytest.mark.asyncio
async def test_evaluate_retrieval_handles_no_matches(
    mock_repository: AsyncMock, sample_documents: list[Document]
) -> None:
    mock_repository.vector_search.return_value = sample_documents
    query = "Unrelated topic"
    expected_ids = ["uuid-999", "uuid-888"]
    k = 3

    result = await evaluate_retrieval(mock_repository, query, None, expected_ids, k)

    assert result.recall_at_k == 0.0
    assert result.precision_at_k == 0.0


@pytest.mark.asyncio
async def test_evaluate_retrieval_handles_empty_results(
    mock_repository: AsyncMock,
) -> None:
    mock_repository.vector_search.return_value = []
    query = "Nothing found"
    expected_ids = ["uuid-001"]
    k = 5

    result = await evaluate_retrieval(mock_repository, query, None, expected_ids, k)

    assert result.recall_at_k == 0.0
    assert result.precision_at_k == 0.0
    assert result.num_retrieved == 0


# ---------------------------------------------------------------------------
# Cache behavior
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_evaluate_retrieval_uses_cache_for_repeated_queries(
    mock_repository: AsyncMock,
    sample_documents: list[Document],
    eval_cache_dir: Path,
) -> None:
    mock_repository.vector_search.return_value = sample_documents
    query = "Cached query"
    expected_ids = ["uuid-001", "uuid-002"]
    k = 3

    with patch("retrieval.evaluate_retrieval.EVAL_CACHE_DIR", eval_cache_dir):
        first_result = await evaluate_retrieval(mock_repository, query, None, expected_ids, k)

        mock_repository.vector_search.assert_called_once()

        second_result = await evaluate_retrieval(mock_repository, query, None, expected_ids, k)

        mock_repository.vector_search.assert_called_once()

    assert first_result.recall_at_k == second_result.recall_at_k
    assert first_result.precision_at_k == second_result.precision_at_k


@pytest.mark.asyncio
async def test_evaluate_retrieval_invalidates_cache_when_expected_ids_change(
    mock_repository: AsyncMock,
    sample_documents: list[Document],
    eval_cache_dir: Path,
) -> None:
    mock_repository.vector_search.return_value = sample_documents
    query = "Same query"
    k = 3

    with patch("retrieval.evaluate_retrieval.EVAL_CACHE_DIR", eval_cache_dir):
        await evaluate_retrieval(mock_repository, query, None, ["uuid-001"], k)

        await evaluate_retrieval(mock_repository, query, None, ["uuid-001", "uuid-002"], k)

    assert mock_repository.vector_search.call_count == 2


@pytest.mark.asyncio
async def test_evaluate_retrieval_invalidates_cache_when_query_changes(
    mock_repository: AsyncMock,
    sample_documents: list[Document],
    eval_cache_dir: Path,
) -> None:
    mock_repository.vector_search.return_value = sample_documents
    expected_ids = ["uuid-001"]
    k = 3

    with patch("retrieval.evaluate_retrieval.EVAL_CACHE_DIR", eval_cache_dir):
        await evaluate_retrieval(mock_repository, "First query", None, expected_ids, k)

        await evaluate_retrieval(mock_repository, "Second query", None, expected_ids, k)

    assert mock_repository.vector_search.call_count == 2


@pytest.mark.asyncio
async def test_evaluate_retrieval_stores_cache_as_json(
    mock_repository: AsyncMock,
    sample_documents: list[Document],
    eval_cache_dir: Path,
) -> None:
    mock_repository.vector_search.return_value = sample_documents
    query = "Store as JSON"
    expected_ids = ["uuid-001", "uuid-002"]
    k = 3

    with patch("retrieval.evaluate_retrieval.EVAL_CACHE_DIR", eval_cache_dir):
        result = await evaluate_retrieval(mock_repository, query, None, expected_ids, k)

    cache_files = list(eval_cache_dir.glob("*.json"))
    assert len(cache_files) == 1

    with cache_files[0].open("r") as f:
        cached_data = json.load(f)

    assert cached_data["recall_at_k"] == result.recall_at_k
    assert cached_data["precision_at_k"] == result.precision_at_k
    assert cached_data["k"] == k


# ---------------------------------------------------------------------------
# k-sweep behavior
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_evaluate_retrieval_handles_different_k_values_independently(
    mock_repository: AsyncMock,
    sample_documents: list[Document],
    eval_cache_dir: Path,
) -> None:
    mock_repository.vector_search.return_value = sample_documents
    query = "k-sweep test"
    expected_ids = ["uuid-001", "uuid-002"]

    with patch("retrieval.evaluate_retrieval.EVAL_CACHE_DIR", eval_cache_dir):
        result_k3 = await evaluate_retrieval(mock_repository, query, None, expected_ids, k=3)
        result_k10 = await evaluate_retrieval(mock_repository, query, None, expected_ids, k=10)

    assert result_k3.k == 3
    assert result_k10.k == 10
    assert mock_repository.vector_search.call_count == 2


# ---------------------------------------------------------------------------
# Error states
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_evaluate_retrieval_raises_error_when_repository_fails(
    mock_repository: AsyncMock,
) -> None:
    mock_repository.vector_search.side_effect = Exception("Connection failed")
    query = "Error query"
    expected_ids = ["uuid-001"]

    with pytest.raises(Exception, match="Connection failed"):
        await evaluate_retrieval(mock_repository, query, None, expected_ids, k=5)
