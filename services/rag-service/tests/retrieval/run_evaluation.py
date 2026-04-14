"""
Standalone evaluation script for agent-driven RAG retrieval quality.

Loads a golden set, runs agent-service queries, extracts chunk IDs used by
RAG MCP tools from the agent response, computes deterministic retrieval metrics,
and saves detailed reports.

Usage:
    uv run python services/rag-service/tests/retrieval/run_evaluation.py

Environment Variables:
    EVAL_MANAGED_SERVICES: Start local rag+agent services from this script (default: 1)
    AGENT_SERVICE_URL: Agent service base URL (default: http://127.0.0.1:8003)
    RAG_SERVICE_URL: RAG service base URL used by managed agent mode (default: http://127.0.0.1:8001)
    AGENT_ANALYZE_PATH: Analyze endpoint path (default: /api/v1/agent/analyze)
    AGENT_MAX_ITERATIONS: Max iterations per agent run (default: 10)
    RETRIEVAL_K: Cutoff k for recall/precision/MRR computation (default: 10)
    RECALL_THRESHOLD: Minimum acceptable recall@k (default: 0.8)
    OUTPUT_FILE: Path to save results JSON (default: evaluation_results.json)
"""

import asyncio
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

# Add rag-service src and current directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))
import ast
import re

from agent_eval_runtime import (
    ChunkResolutionIndex,
    ManagedServiceStack,
    load_chunk_resolution_index,
    resolve_document_chunk_id,
)
from common.logging import configure_logging, get_logger
from evaluate_retrieval import RetrievalMetrics, compute_metrics
from golden_set import load_golden_set

logger = get_logger(__name__)

RAG_TOOL_NAMES = {
    "search_knowledge_base",
    "expand_graph_by_ids",
    "get_entity_by_number",
    "get_related_code_definitions",
    "get_search_tags_catalog",
}

VERBOSE_STEPS = os.getenv("EVAL_VERBOSE", "1") not in {"0", "false", "False"}


def _step(message: str, **details: Any) -> None:
    """Print/log a single evaluation step with compact key results."""
    payload = ", ".join(f"{key}={value}" for key, value in details.items())
    line = f"[STEP] {message}" + (f" | {payload}" if payload else "")
    logger.info("eval_step", message=message, **details)
    if VERBOSE_STEPS:
        print(line)


def _get_agent_params() -> dict[str, Any]:
    """Get evaluation runtime params from environment."""
    return {
        "managed_services": os.getenv("EVAL_MANAGED_SERVICES", "1") not in {"0", "false", "False"},
        "base_url": os.getenv("AGENT_SERVICE_URL", "http://127.0.0.1:8003").rstrip("/"),
        "rag_base_url": os.getenv("RAG_SERVICE_URL", "http://127.0.0.1:8001").rstrip("/"),
        "analyze_path": os.getenv("AGENT_ANALYZE_PATH", "/api/v1/agent/analyze"),
        "max_iterations": int(os.getenv("AGENT_MAX_ITERATIONS", "10")),
    }


def _normalize_path(path: str) -> str:
    if path.startswith("/"):
        return path
    return f"/{path}"


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _extract_chunk_id(document: Any) -> str | None:
    if not isinstance(document, dict):
        return None

    metadata = document.get("metadata")
    if isinstance(metadata, dict):
        chunk_id = metadata.get("chunk_id")
        if isinstance(chunk_id, str) and chunk_id.strip():
            return chunk_id.strip()

    direct_chunk_id = document.get("chunk_id")
    if isinstance(direct_chunk_id, str) and direct_chunk_id.strip():
        return direct_chunk_id.strip()

    direct_id = document.get("id")
    if isinstance(direct_id, str) and direct_id.strip():
        return direct_id.strip()

    return None


def _collect_chunk_ids(value: Any) -> list[str]:
    """Collect chunk IDs from nested MCP/tool payloads."""
    chunk_ids: list[str] = []

    if isinstance(value, list):
        for item in value:
            chunk_ids.extend(_collect_chunk_ids(item))
        return _dedupe_preserve_order(chunk_ids)

    if not isinstance(value, dict):
        return []

    maybe_chunk_id = _extract_chunk_id(value)
    if maybe_chunk_id:
        chunk_ids.append(maybe_chunk_id)

    for key in ("documents", "results", "expanded", "document", "data", "result"):
        if key in value:
            chunk_ids.extend(_collect_chunk_ids(value[key]))

    return _dedupe_preserve_order(chunk_ids)


def _collect_documents(value: Any) -> list[dict[str, Any]]:
    """Collect document-like records from nested MCP/tool payloads."""
    documents: list[dict[str, Any]] = []

    if isinstance(value, list):
        for item in value:
            documents.extend(_collect_documents(item))
        return documents

    if not isinstance(value, dict):
        return documents

    if any(field in value for field in ("id", "chunk_id", "metadata", "content")):
        documents.append(value)

    for key in ("documents", "results", "expanded", "document", "data", "result"):
        if key in value:
            documents.extend(_collect_documents(value[key]))

    return documents


def _extract_usage_from_response(
    response_payload: dict[str, Any],
    chunk_index: ChunkResolutionIndex,
) -> dict[str, Any]:
    """Extract global and per-tool chunk usage from agent response."""
    tool_executions = response_payload.get("tool_executions")
    per_tool: list[dict[str, Any]] = []
    all_chunk_ids: list[str] = []

    _step(
        "extract_usage_start",
        has_tool_executions=isinstance(tool_executions, list),
        tool_execution_count=len(tool_executions) if isinstance(tool_executions, list) else 0,
    )

    if isinstance(tool_executions, list):
        for tool_execution in tool_executions:
            if not isinstance(tool_execution, dict):
                continue

            tool_name = tool_execution.get("tool_name")
            if not isinstance(tool_name, str) or tool_name not in RAG_TOOL_NAMES:
                continue

            raw_result = tool_execution.get("result")
            parsed_result: Any = raw_result

            if isinstance(raw_result, str):
                match = re.search(r"data=(\{.*\})\s+error=", raw_result, re.DOTALL)
                if match:
                    try:
                        parsed_result = ast.literal_eval(match.group(1)).get("result")
                        _step("tool_result_parsed_from_string", tool_name=tool_name, parsed=True)
                    except (SyntaxError, ValueError, AttributeError) as parse_error:
                        _step(
                            "tool_result_parse_failed",
                            tool_name=tool_name,
                            error=str(parse_error),
                        )
                else:
                    _step("tool_result_parse_skipped", tool_name=tool_name, reason="regex_no_match")

            documents = _collect_documents(parsed_result)
            resolved_ids: list[str] = []
            unresolved_ids: list[str] = []

            for document in documents:
                resolved_chunk_id, resolution_strategy = resolve_document_chunk_id(
                    document, chunk_index
                )
                if resolved_chunk_id is None:
                    raw_id = document.get("id")
                    if isinstance(raw_id, str) and raw_id.strip():
                        unresolved_ids.append(raw_id.strip())
                    continue
                resolved_ids.append(resolved_chunk_id)
                _step(
                    "document_resolved",
                    tool_name=tool_name,
                    chunk_id=resolved_chunk_id,
                    strategy=resolution_strategy,
                )

            deduped_resolved = _dedupe_preserve_order(resolved_ids)
            all_chunk_ids.extend(deduped_resolved)
            per_tool.append(
                {
                    "tool_name": tool_name,
                    "chunk_ids": deduped_resolved,
                    "chunk_count": len(deduped_resolved),
                    "unresolved_ids": _dedupe_preserve_order(unresolved_ids),
                    "error": tool_execution.get("error"),
                }
            )
            _step(
                "tool_processed",
                tool_name=tool_name,
                documents=len(documents),
                resolved=len(deduped_resolved),
                unresolved=len(unresolved_ids),
            )

    if not all_chunk_ids:
        citations = response_payload.get("citations")
        if isinstance(citations, list):
            for citation in citations:
                if not isinstance(citation, dict):
                    continue
                chunk_id = citation.get("chunk_id")
                if isinstance(chunk_id, str) and chunk_id.strip():
                    all_chunk_ids.append(chunk_id.strip())
            _step("usage_fallback_to_citations", citation_count=len(citations))

    used_rag_tools = [
        tool_info["tool_name"]
        for tool_info in per_tool
        if isinstance(tool_info.get("tool_name"), str)
    ]

    deduped_ids = _dedupe_preserve_order(all_chunk_ids)
    _step(
        "extract_usage_done",
        retrieved_ids=len(deduped_ids),
        used_tools=len(used_rag_tools),
    )

    return {
        "retrieved_ids": deduped_ids,
        "per_tool": per_tool,
        "used_rag_tools": _dedupe_preserve_order(used_rag_tools),
    }


async def _run_agent_query(
    client: httpx.AsyncClient,
    analyze_path: str,
    query: str,
    max_iterations: int,
) -> tuple[dict[str, Any], float]:
    payload = {
        "query": query,
        "context": {},
        "max_iterations": max_iterations,
    }

    _step("agent_request_start", query=query, max_iterations=max_iterations)
    start_time = time.perf_counter()
    response = await client.post(analyze_path, json=payload)
    latency_ms = (time.perf_counter() - start_time) * 1000

    _step(
        "agent_request_done",
        status_code=response.status_code,
        latency_ms=round(latency_ms, 2),
    )
    response.raise_for_status()
    response_payload = response.json()
    if not isinstance(response_payload, dict):
        raise ValueError("Agent analyze response is not a JSON object")

    _step(
        "agent_response_parsed",
        status=response_payload.get("status"),
        tools_used=len(response_payload.get("tools_used", [])),
    )
    return response_payload, latency_ms


def _build_metrics(
    retrieved_ids: list[str],
    expected_chunk_ids: list[str],
    k: int,
    latency_ms: float,
) -> RetrievalMetrics:
    base_metrics = compute_metrics(
        retrieved_ids=retrieved_ids, expected_ids=expected_chunk_ids, k=k
    )
    return RetrievalMetrics(
        recall_at_k=base_metrics.recall_at_k,
        precision_at_k=base_metrics.precision_at_k,
        mrr_at_k=base_metrics.mrr_at_k,
        latency_ms=latency_ms,
        k=k,
        num_retrieved=len(retrieved_ids),
        num_expected=len(expected_chunk_ids),
        retrieved_ids=retrieved_ids,
    )


def _print_metrics(case_id: str, query: str, metrics: RetrievalMetrics, threshold: float) -> None:
    """Print metrics for a single test case."""
    status = "PASS" if metrics.recall_at_k >= threshold else "FAIL"
    print(
        f"[{status}] {case_id}: recall={metrics.recall_at_k:.2f}, "
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


def _load_content_map(enriched_path: Path) -> dict[str, str]:
    """Load chunk_id -> content mapping from ULTIMATE_BOOK_DATA_enriched.json."""
    if not enriched_path.exists():
        logger.warning("enriched_data_not_found", path=str(enriched_path))
        return {}
    with enriched_path.open(encoding="utf-8") as f:
        data = json.load(f)
    return {item["chunk_id"]: item.get("content", "") for item in data if "chunk_id" in item}


def _save_error_report(results: list[dict], output_path: Path, content_map: dict[str, str]) -> None:
    """Save a human-readable error report showing retrieved vs expected chunks per query."""
    lines: list[str] = []
    question_num = 0

    for case in results:
        expected_chunks = {
            c["chunk_id"]: content_map.get(c["chunk_id"], "") for c in case["expected_chunks"]
        }

        for query_result in case["queries"]:
            question_num += 1
            query = query_result["query"]
            retrieved_ids: list[str] = query_result.get("retrieved_ids", [])
            retrieved_set = set(retrieved_ids)
            metrics = query_result["metrics"]

            lines.append(f"Question {question_num} [{case['test_case_id']}]")
            lines.append(f"Query: {query}")
            lines.append(
                f"recall={metrics['recall_at_k']:.2f}, "
                f"precision={metrics['precision_at_k']:.2f}, "
                f"mrr={metrics['mrr_at_k']:.2f}"
            )
            lines.append(f"RAG tools used: {', '.join(query_result.get('used_rag_tools', []))}")
            lines.append("")

            for chunk_id, content in expected_chunks.items():
                status = "PASS" if chunk_id in retrieved_set else "MISS"
                lines.append(f"  [{status}] {chunk_id}: {content}")

            extra_chunks = [
                chunk_id for chunk_id in retrieved_ids if chunk_id not in expected_chunks
            ]
            if extra_chunks:
                lines.append("")
                lines.append("  Extra chunks:")
                for chunk_id in extra_chunks:
                    lines.append(f"    - {chunk_id}")

            lines.append("")
            lines.append("")

    with output_path.open("w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    logger.info("error_report_saved", path=str(output_path), question_count=question_num)


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
    _step("evaluation_start")
    configure_logging(service_name="retrieval_evaluation")

    k = int(os.getenv("RETRIEVAL_K", "10"))
    threshold = float(os.getenv("RECALL_THRESHOLD", "0.8"))
    # Default output path is in the same directory as this script
    default_output = Path(__file__).parent / "evaluation_results.json"
    output_file = Path(os.getenv("OUTPUT_FILE", str(default_output)))
    error_report_file = output_file.with_name(output_file.stem + "_error_report.txt")

    agent_params = _get_agent_params()
    analyze_path = _normalize_path(str(agent_params["analyze_path"]))

    golden_set_path = Path(__file__).parent / "golden_set_converted3.json"
    enriched_path = Path(__file__).parent / "ULTIMATE_BOOK_DATA_enriched.json"
    content_map = _load_content_map(enriched_path)
    chunk_index = load_chunk_resolution_index(enriched_path)

    _step(
        "runtime_config_loaded",
        k=k,
        threshold=threshold,
        managed_services=agent_params["managed_services"],
        agent_url=agent_params["base_url"],
        rag_url=agent_params["rag_base_url"],
        chunk_map_size=len(chunk_index.uuid_to_chunk_id),
    )

    logger.info("loading_golden_set", path=str(golden_set_path))
    test_cases = load_golden_set(golden_set_path)
    logger.info("golden_set_loaded", count=len(test_cases))
    _step("golden_set_ready", test_cases=len(test_cases))

    evaluation_results: list[dict[str, Any]] = []
    all_metrics: list[RetrievalMetrics] = []

    print(f"Evaluating {len(test_cases)} test cases with k={k}, threshold={threshold}")
    print(f"Agent endpoint: {agent_params['base_url']}{analyze_path}")
    print(f"Managed services mode: {agent_params['managed_services']}")
    print("=" * 60)

    project_root = Path(__file__).resolve().parents[4]
    _step("managed_service_stack_start")
    with ManagedServiceStack(
        project_root=project_root,
        start_services=bool(agent_params["managed_services"]),
        rag_base_url=str(agent_params["rag_base_url"]),
        agent_base_url=str(agent_params["base_url"]),
    ):
        _step("managed_service_stack_ready")
        async with httpx.AsyncClient(
            base_url=str(agent_params["base_url"]), timeout=300.0
        ) as client:
            for case in test_cases:
                queries_to_test = [case.base_query] + case.paraphrases
                case_results: list[dict[str, Any]] = []
                expected_chunk_ids = [chunk.chunk_id for chunk in case.expected_chunks]
                _step(
                    "case_start",
                    case_id=case.id,
                    queries=len(queries_to_test),
                    expected_chunks=len(expected_chunk_ids),
                )

                for query in queries_to_test:
                    query_type = "base_query" if query == case.base_query else "paraphrase"
                    _step("query_start", case_id=case.id, query_type=query_type)

                    try:
                        agent_response, latency_ms = await _run_agent_query(
                            client=client,
                            analyze_path=analyze_path,
                            query=query,
                            max_iterations=int(agent_params["max_iterations"]),
                        )
                        usage = _extract_usage_from_response(agent_response, chunk_index)
                        retrieved_ids = usage["retrieved_ids"]
                        metrics = _build_metrics(retrieved_ids, expected_chunk_ids, k, latency_ms)
                        error: str | None = None
                    except Exception as exc:
                        logger.error(
                            "agent_query_failed",
                            case_id=case.id,
                            query_type=query_type,
                            error=str(exc),
                        )
                        _step(
                            "query_failed", case_id=case.id, query_type=query_type, error=str(exc)
                        )
                        metrics = _build_metrics([], expected_chunk_ids, k, latency_ms=0.0)
                        usage = {
                            "retrieved_ids": [],
                            "per_tool": [],
                            "used_rag_tools": [],
                        }
                        agent_response = {}
                        error = str(exc)

                    all_metrics.append(metrics)
                    _print_metrics(case.id, query, metrics, threshold)
                    _step(
                        "query_done",
                        case_id=case.id,
                        query_type=query_type,
                        retrieved=len(usage["retrieved_ids"]),
                        recall=round(metrics.recall_at_k, 4),
                        precision=round(metrics.precision_at_k, 4),
                        passed=metrics.recall_at_k >= threshold,
                    )

                    case_results.append(
                        {
                            "query": query,
                            "query_type": query_type,
                            "metrics": metrics.model_dump(),
                            "retrieved_ids": usage["retrieved_ids"],
                            "used_rag_tools": usage["used_rag_tools"],
                            "rag_tool_chunk_trace": usage["per_tool"],
                            "agent_status": agent_response.get("status"),
                            "agent_tools_used": agent_response.get("tools_used", []),
                            "passed": metrics.recall_at_k >= threshold,
                            "error": error,
                        }
                    )

                avg_recall = round(
                    sum(result["metrics"]["recall_at_k"] for result in case_results)
                    / len(case_results),
                    4,
                )
                _step("case_done", case_id=case.id, avg_recall=avg_recall)

                evaluation_results.append(
                    {
                        "test_case_id": case.id,
                        "description": case.description,
                        "expected_chunks": [chunk.model_dump() for chunk in case.expected_chunks],
                        "split": case.split,
                        "queries": case_results,
                        "avg_recall": avg_recall,
                        "all_passed": all(result["passed"] for result in case_results),
                    }
                )

    summary_stats = _compute_summary_stats(all_metrics)
    summary_stats["total_cases"] = len(test_cases)
    summary_stats["total_queries"] = len(all_metrics)
    summary_stats["passed_queries"] = sum(
        1 for metric in all_metrics if metric.recall_at_k >= threshold
    )
    summary_stats["pass_rate"] = round(
        summary_stats["passed_queries"] / len(all_metrics) if all_metrics else 0.0,
        4,
    )
    _step(
        "summary_ready",
        total_queries=summary_stats["total_queries"],
        passed_queries=summary_stats["passed_queries"],
        pass_rate=summary_stats["pass_rate"],
    )

    config = {
        "k": k,
        "recall_threshold": threshold,
        "managed_services": agent_params["managed_services"],
        "agent_service_url": agent_params["base_url"],
        "rag_service_url": agent_params["rag_base_url"],
        "agent_analyze_path": analyze_path,
        "agent_max_iterations": agent_params["max_iterations"],
        "golden_set_path": str(golden_set_path),
        "uuid_map_size": len(chunk_index.uuid_to_chunk_id),
    }

    _save_results(evaluation_results, summary_stats, config, output_file)
    _save_error_report(evaluation_results, error_report_file, content_map)
    _print_summary(
        total=len(all_metrics),
        passed=summary_stats["passed_queries"],
        threshold=threshold,
        summary_stats=summary_stats,
    )

    print(f"\nResults saved to: {output_file}")
    print(f"Error report saved to: {error_report_file}")

    failed_count = sum(1 for metric in all_metrics if metric.recall_at_k < threshold)
    _step("evaluation_done", failed_queries=failed_count)
    return 1 if failed_count > 0 else 0


if __name__ == "__main__":
    exit_code = asyncio.run(run_evaluation())
    sys.exit(exit_code)
