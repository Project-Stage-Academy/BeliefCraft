"""
Retrieval evaluation with deterministic metrics and caching.

Provides recall@k, precision@k, MRR@k, and latency measurements for RAG retrieval quality.
No LLM judge — metrics are computed from ground-truth chunk IDs.
"""

import hashlib
import json
import time
from pathlib import Path

from common.logging import get_logger
from pydantic import BaseModel
from rag_service.models import MetadataFilters, SearchFilters
from rag_service.repositories import AbstractVectorStoreRepository

logger = get_logger(__name__)

EVAL_CACHE_DIR = Path(__file__).parent / ".eval_cache"


class RetrievalMetrics(BaseModel):
    """Metrics for retrieval quality evaluation.

    Args:
        recall_at_k: Fraction of expected chunks found in top-k results.
        precision_at_k: Fraction of top-k results that are expected chunks.
        mrr_at_k: Mean Reciprocal Rank - measures ranking quality (1/(rank of first hit)).
        latency_ms: Wall-clock time from query submission to results.
        k: Number of top results requested.
        num_retrieved: Actual number of documents retrieved.
        num_expected: Number of ground-truth chunk IDs.
    """

    recall_at_k: float
    precision_at_k: float
    mrr_at_k: float
    latency_ms: float
    k: int
    num_retrieved: int
    num_expected: int


def compute_metrics(retrieved_ids: list[str], expected_ids: list[str], k: int) -> RetrievalMetrics:
    """Compute recall@k, precision@k, and MRR@k from retrieved and expected chunk IDs.

    Args:
        retrieved_ids: IDs of documents returned by the retrieval system.
        expected_ids: Ground-truth IDs that should have been retrieved.
        k: Number of top results requested.

    Returns:
        RetrievalMetrics with recall, precision, and MRR scores.
    """
    retrieved_set = set(retrieved_ids[:k])
    expected_set = set(expected_ids)
    intersection = retrieved_set & expected_set

    recall = len(intersection) / len(expected_set) if expected_set else 0.0
    precision = len(intersection) / k if k > 0 else 0.0

    mrr = 0.0
    for idx, doc_id in enumerate(retrieved_ids[:k]):
        if doc_id in expected_set:
            mrr = 1 / (idx + 1)
            break

    return RetrievalMetrics(
        recall_at_k=recall,
        precision_at_k=precision,
        mrr_at_k=mrr,
        latency_ms=0.0,
        k=k,
        num_retrieved=len(retrieved_ids),
        num_expected=len(expected_ids),
    )


def _convert_search_filters(filters: SearchFilters | None) -> MetadataFilters | None:
    """Convert SearchFilters to MetadataFilters for repository queries."""
    if filters is None:
        logger.debug("No filters provided to _convert_search_filters.")
        return None

    from rag_service.models import MetadataFilter, MetadataFilterOperator

    metadata_filters = []

    if filters.part is not None:
        metadata_filters.append(
            MetadataFilter(field="part", operator=MetadataFilterOperator.EQ, value=filters.part)
        )
        logger.debug("Added filter for part: %s", filters.part)
    if filters.section is not None:
        metadata_filters.append(
            MetadataFilter(
                field="section_number", operator=MetadataFilterOperator.EQ, value=filters.section
            )
        )
        logger.debug("Added filter for section: %s", filters.section)
    if filters.subsection is not None:
        metadata_filters.append(
            MetadataFilter(
                field="subsection_number",
                operator=MetadataFilterOperator.EQ,
                value=filters.subsection,
            )
        )
        logger.debug("Added filter for subsection: %s", filters.subsection)
    if filters.subsubsection is not None:
        metadata_filters.append(
            MetadataFilter(
                field="subsubsection_number",
                operator=MetadataFilterOperator.EQ,
                value=filters.subsubsection,
            )
        )
        logger.debug("Added filter for subsubsection: %s", filters.subsubsection)
    if filters.page_number is not None:
        metadata_filters.append(
            MetadataFilter(
                field="page_number",
                operator=MetadataFilterOperator.EQ,
                value=filters.page_number,
            )
        )
        logger.debug("Added filter for page_number: %s", filters.page_number)

    logger.debug("Converted filters: %s", metadata_filters)
    return MetadataFilters(filters=metadata_filters, condition="and") if metadata_filters else None


def _get_cache_key(
    query: str, filters: SearchFilters | None, expected_ids: list[str], k: int
) -> str:
    """Generate cache key from query parameters."""
    filter_data = filters.model_dump(exclude_none=True) if filters else {}
    cache_data = {
        "query": query.strip().lower(),
        "filters": filter_data,
        "expected_ids": sorted(expected_ids),
        "k": k,
    }
    cache_str = json.dumps(cache_data, sort_keys=True)
    return hashlib.sha256(cache_str.encode()).hexdigest()


def _load_from_cache(cache_key: str) -> RetrievalMetrics | None:
    """Load metrics from cache file if it exists."""
    EVAL_CACHE_DIR.mkdir(exist_ok=True)
    cache_file = EVAL_CACHE_DIR / f"{cache_key}.json"

    if cache_file.exists():
        with cache_file.open("r") as f:
            data = json.load(f)
        return RetrievalMetrics(**data)

    return None


def _save_to_cache(cache_key: str, metrics: RetrievalMetrics) -> None:
    """Save metrics to cache file."""
    EVAL_CACHE_DIR.mkdir(exist_ok=True)
    cache_file = EVAL_CACHE_DIR / f"{cache_key}.json"

    with cache_file.open("w") as f:
        json.dump(metrics.model_dump(), f, indent=2)


async def evaluate_retrieval(
    repository: AbstractVectorStoreRepository,
    query: str,
    filters: SearchFilters | None,
    expected_chunk_ids: list[str],
    k: int = 10,
) -> RetrievalMetrics:
    """Evaluate retrieval quality with deterministic metrics.

    Args:
        repository: Vector store repository to query.
        query: Text query for semantic search.
        filters: Optional metadata filters to apply.
        expected_chunk_ids: Ground-truth chunk IDs that should be retrieved.
        k: Number of top results to return.

    Returns:
        RetrievalMetrics with recall@k, precision@k, MRR@k, and latency.
    """
    logger.debug("Starting evaluate_retrieval with query: %s", query)
    logger.debug("Filters provided: %s", filters)

    cache_key = _get_cache_key(query, filters, expected_chunk_ids, k)

    cached_metrics = _load_from_cache(cache_key)
    if cached_metrics is not None:
        logger.debug("Cache hit for key: %s", cache_key)
        return cached_metrics

    metadata_filters = _convert_search_filters(filters)
    logger.debug("Converted metadata filters: %s", metadata_filters)

    start_time = time.perf_counter()
    documents = await repository.vector_search(query, k, metadata_filters)
    end_time = time.perf_counter()

    logger.debug("Retrieved documents: %s", documents)

    latency_ms = (end_time - start_time) * 1000

    retrieved_ids = [doc.id for doc in documents]

    metrics = compute_metrics(retrieved_ids, expected_chunk_ids, k)

    final_metrics = RetrievalMetrics(
        recall_at_k=metrics.recall_at_k,
        precision_at_k=metrics.precision_at_k,
        mrr_at_k=metrics.mrr_at_k,
        latency_ms=latency_ms,
        k=k,
        num_retrieved=len(retrieved_ids),
        num_expected=len(expected_chunk_ids),
    )

    logger.debug("Final metrics: %s", final_metrics)

    _save_to_cache(cache_key, final_metrics)

    return final_metrics
