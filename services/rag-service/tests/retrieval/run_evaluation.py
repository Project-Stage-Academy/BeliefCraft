#!/usr/bin/env python3
"""
Standalone evaluation script for RAG retrieval quality.

Loads golden_set.json, connects to Weaviate, evaluates each test case,
saves results to JSON, and prints aggregated metrics. No pytest required.

Usage:
    uv run python services/rag-service/tests/retrieval/run_evaluation.py

Environment Variables:
    WEAVIATE_HOST: Weaviate host (default: localhost)
    WEAVIATE_PORT: Weaviate port (default: 8080)
    WEAVIATE_GRPC_PORT: Weaviate gRPC port (default: 50051)
    RETRIEVAL_K: Number of top results to evaluate (default: 10)
    RECALL_THRESHOLD: Minimum acceptable recall@k (default: 0.8)
    OUTPUT_FILE: Path to save results JSON (default: evaluation_results.json)
"""

import asyncio
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

# Add rag-service src and current directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from common.logging import configure_logging, get_logger
from evaluate_retrieval import RetrievalMetrics, evaluate_retrieval
from golden_set import load_golden_set
from rag_service.config import Settings
from rag_service.repositories import WeaviateRepository

logger = get_logger(__name__)


def _get_weaviate_params() -> dict:
    """Get Weaviate connection parameters from environment."""
    return {
        "host": os.getenv("WEAVIATE_HOST", "localhost"),
        "port": int(os.getenv("WEAVIATE_PORT", "8080")),
        "grpc_port": int(os.getenv("WEAVIATE_GRPC_PORT", "50051")),
    }


def _print_metrics(case_id: str, query: str, metrics: RetrievalMetrics, threshold: float) -> None:
    """Print metrics for a single test case."""
    status = "✓" if metrics.recall_at_k >= threshold else "✗"
    print(
        f"{status} {case_id}: recall={metrics.recall_at_k:.2f}, "
        f"precision={metrics.precision_at_k:.2f}, mrr={metrics.mrr_at_k:.2f}, "
        f"latency={metrics.latency_ms:.1f}ms"
    )
    if metrics.recall_at_k < threshold:
        print(f"  Query: {query}")
        print(f"  Warning: Recall {metrics.recall_at_k:.2f} below threshold {threshold:.2f}")


def _compute_summary_stats(all_metrics: list[RetrievalMetrics]) -> dict:
    """Compute aggregated statistics from all metrics."""
    total = len(all_metrics)
    if total == 0:
        return {
            "avg_recall_at_k": 0.0,
            "avg_precision_at_k": 0.0,
            "avg_mrr_at_k": 0.0,
            "avg_latency_ms": 0.0,
            "min_recall_at_k": 0.0,
            "max_recall_at_k": 0.0,
        }

    recall_values = [m.recall_at_k for m in all_metrics]
    precision_values = [m.precision_at_k for m in all_metrics]
    mrr_values = [m.mrr_at_k for m in all_metrics]
    latency_values = [m.latency_ms for m in all_metrics]

    return {
        "avg_recall_at_k": round(sum(recall_values) / total, 4),
        "avg_precision_at_k": round(sum(precision_values) / total, 4),
        "avg_mrr_at_k": round(sum(mrr_values) / total, 4),
        "avg_latency_ms": round(sum(latency_values) / total, 2),
        "min_recall_at_k": round(min(recall_values), 4),
        "max_recall_at_k": round(max(recall_values), 4),
        "min_latency_ms": round(min(latency_values), 2),
        "max_latency_ms": round(max(latency_values), 2),
    }


def _save_results(
    results: list[dict],
    summary_stats: dict,
    config: dict,
    output_path: Path,
) -> None:
    """Save evaluation results to JSON file."""
    output_data = {
        "timestamp": datetime.now(UTC).isoformat(),
        "config": config,
        "summary": summary_stats,
        "test_cases": results,
    }

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)

    logger.info("results_saved", path=str(output_path), test_count=len(results))


def _print_summary(
    total: int,
    passed: int,
    threshold: float,
    summary_stats: dict,
) -> None:
    """Print aggregated metrics summary."""
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total cases: {total}")
    print(f"Passed (recall >= {threshold:.2f}): {passed}/{total} ({passed/total*100:.1f}%)")
    print(f"Average recall@k: {summary_stats['avg_recall_at_k']:.3f}")
    print(f"Average precision@k: {summary_stats['avg_precision_at_k']:.3f}")
    print(f"Average MRR@k: {summary_stats['avg_mrr_at_k']:.3f}")
    print(f"Average latency: {summary_stats['avg_latency_ms']:.1f}ms")
    print(
        f"Min/Max recall@k: {summary_stats['min_recall_at_k']:.3f} / "
        f"{summary_stats['max_recall_at_k']:.3f}"
    )
    print("=" * 60)


async def run_evaluation() -> int:
    """Run evaluation on all golden set test cases.

    Returns:
        Exit code: 0 if all tests pass, 1 if any test fails.
    """
    configure_logging(service_name="retrieval_evaluation")

    k = int(os.getenv("RETRIEVAL_K", "10"))
    threshold = float(os.getenv("RECALL_THRESHOLD", "0.8"))

    # Default output path is in the same directory as this script
    default_output = Path(__file__).parent / "evaluation_results.json"
    output_file = Path(os.getenv("OUTPUT_FILE", str(default_output)))

    weaviate_params = _get_weaviate_params()
    logger.info("weaviate_connection", **weaviate_params)

    settings = Settings(
        repository="WeaviateRepository",
        weaviate_host=weaviate_params["host"],
        weaviate_port=weaviate_params["port"],
        weaviate_grpc_port=weaviate_params["grpc_port"],
    )

    golden_set_path = Path(__file__).parent / "golden_set.json"
    logger.info("loading_golden_set", path=str(golden_set_path))
    test_cases = load_golden_set(golden_set_path)
    logger.info("golden_set_loaded", count=len(test_cases))

    evaluation_results: list[dict] = []
    all_metrics: list[RetrievalMetrics] = []

    async with WeaviateRepository(settings) as repository:
        logger.info("weaviate_connected", collection=repository._collection.name)

        print(f"Evaluating {len(test_cases)} test cases with k={k}, threshold={threshold}")
        print("=" * 60)

        for case in test_cases:
            queries_to_test = [case.base_query] + case.paraphrases
            case_results: list[dict] = []
            expected_chunk_ids = [chunk.chunk_id for chunk in case.expected_chunks]

            for query in queries_to_test:
                metrics = await evaluate_retrieval(
                    repository=repository,
                    query=query,
                    expected_chunk_ids=expected_chunk_ids,
                    k=k,
                )

                all_metrics.append(metrics)
                _print_metrics(case.id, query, metrics, threshold)

                case_results.append(
                    {
                        "query": query,
                        "query_type": "base_query" if query == case.base_query else "paraphrase",
                        "metrics": metrics.model_dump(),
                        "passed": metrics.recall_at_k >= threshold,
                    }
                )

            avg_recall = round(
                sum(r["metrics"]["recall_at_k"] for r in case_results) / len(case_results), 4
            )
            evaluation_results.append(
                {
                    "test_case_id": case.id,
                    "description": case.description,
                    "expected_chunks": [chunk.model_dump() for chunk in case.expected_chunks],
                    "split": case.split,
                    "queries": case_results,
                    "avg_recall": avg_recall,
                    "all_passed": all(r["passed"] for r in case_results),
                }
            )

    summary_stats = _compute_summary_stats(all_metrics)
    summary_stats["total_cases"] = len(test_cases)
    summary_stats["total_queries"] = len(all_metrics)
    summary_stats["passed_queries"] = sum(1 for m in all_metrics if m.recall_at_k >= threshold)
    summary_stats["pass_rate"] = round(
        summary_stats["passed_queries"] / len(all_metrics) if all_metrics else 0.0, 4
    )

    config = {
        "k": k,
        "recall_threshold": threshold,
        "weaviate_host": weaviate_params["host"],
        "weaviate_port": weaviate_params["port"],
        "golden_set_path": str(golden_set_path),
    }

    _save_results(evaluation_results, summary_stats, config, output_file)

    _print_summary(
        total=len(all_metrics),
        passed=summary_stats["passed_queries"],
        threshold=threshold,
        summary_stats=summary_stats,
    )

    print(f"\nResults saved to: {output_file}")

    failed_count = sum(1 for m in all_metrics if m.recall_at_k < threshold)
    return 1 if failed_count > 0 else 0


if __name__ == "__main__":
    exit_code = asyncio.run(run_evaluation())
    sys.exit(exit_code)
