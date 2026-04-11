"""
Retrieval evaluation with deterministic metrics.

Provides recall@k, precision@k, MRR@k, and latency measurements for RAG retrieval quality.
No LLM judge — metrics are computed from ground-truth chunk IDs (stable parser IDs).
"""

import time

from common.logging import get_logger
from pydantic import BaseModel
from rag_service.repositories import AbstractVectorStoreRepository

logger = get_logger(__name__)


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


async def evaluate_retrieval(
    repository: AbstractVectorStoreRepository,
    query: str,
    expected_chunk_ids: list[str],
    k: int = 10,
) -> RetrievalMetrics:
    """Evaluate retrieval quality with deterministic metrics.

    Retrieves documents using semantic search, extracts chunk_id from metadata,
    and computes recall@k, precision@k, and MRR@k by comparing with ground truth.

    Args:
        repository: Vector store repository to query.
        query: Text query for semantic search.
        expected_chunk_ids: Ground-truth chunk IDs (stable parser IDs like 'text_7a0afb97').
        k: Number of top results to return.

    Returns:
        RetrievalMetrics with recall@k, precision@k, MRR@k, and latency.
    """
    logger.debug("evaluate_retrieval", query=query, expected_count=len(expected_chunk_ids), k=k)

    start_time = time.perf_counter()
    documents = await repository.vector_search(query, k, filters=None)
    end_time = time.perf_counter()

    latency_ms = (end_time - start_time) * 1000

    # Extract chunk_id from metadata (fallback to UUID if chunk_id not present)
    retrieved_ids = [doc.metadata.get("chunk_id", doc.id) for doc in documents]

    logger.debug(
        "retrieval_complete",
        retrieved_count=len(retrieved_ids),
        latency_ms=f"{latency_ms:.2f}",
    )

    metrics = compute_metrics(retrieved_ids, expected_chunk_ids, k)

    return RetrievalMetrics(
        recall_at_k=metrics.recall_at_k,
        precision_at_k=metrics.precision_at_k,
        mrr_at_k=metrics.mrr_at_k,
        latency_ms=latency_ms,
        k=k,
        num_retrieved=len(retrieved_ids),
        num_expected=len(expected_chunk_ids),
    )
