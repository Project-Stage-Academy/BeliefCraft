"""
Generate aggregated evaluation report from cached metrics.

Usage:
    uv run python services/rag-service/tests/retrieval/generate_eval_report.py
"""

import json
import statistics
from pathlib import Path


def load_all_cached_metrics(cache_dir: Path) -> list[dict]:
    """Load all cached evaluation metrics from .eval_cache directory."""
    metrics = []
    for cache_file in cache_dir.glob("*.json"):
        try:
            with cache_file.open("r") as f:
                data = json.load(f)
                metrics.append(data)
        except Exception as exc:
            print(f"Warning: Failed to load {cache_file}: {exc}")
    return metrics


def aggregate_by_k(metrics: list[dict]) -> dict:
    """Group metrics by k value and compute statistics."""
    by_k = {}

    for metric in metrics:
        k = metric["k"]
        if k not in by_k:
            by_k[k] = {
                "recall": [],
                "precision": [],
                "mrr": [],
                "latency_ms": [],
            }
        by_k[k]["recall"].append(metric["recall_at_k"])
        by_k[k]["precision"].append(metric["precision_at_k"])
        by_k[k]["mrr"].append(metric.get("mrr_at_k", 0.0))
        by_k[k]["latency_ms"].append(metric["latency_ms"])

    def safe_stat(f, arr, default=0.0):
        try:
            return f(arr) if arr else default
        except Exception:
            return default

    aggregated = {}
    for k, values in by_k.items():
        aggregated[f"k={k}"] = {
            "count": len(values["recall"]),
            "recall_at_k": {
                "mean": safe_stat(statistics.mean, values["recall"]),
                "median": safe_stat(statistics.median, values["recall"]),
                "min": safe_stat(min, values["recall"]),
                "max": safe_stat(max, values["recall"]),
                "stdev": statistics.stdev(values["recall"]) if len(values["recall"]) > 1 else 0.0,
            },
            "precision_at_k": {
                "mean": safe_stat(statistics.mean, values["precision"]),
                "median": safe_stat(statistics.median, values["precision"]),
                "min": safe_stat(min, values["precision"]),
                "max": safe_stat(max, values["precision"]),
                "stdev": (
                    statistics.stdev(values["precision"]) if len(values["precision"]) > 1 else 0.0
                ),
            },
            "mrr_at_k": {
                "mean": safe_stat(statistics.mean, values["mrr"]),
                "median": safe_stat(statistics.median, values["mrr"]),
                "min": safe_stat(min, values["mrr"]),
                "max": safe_stat(max, values["mrr"]),
            },
            "latency_ms": {
                "mean": safe_stat(statistics.mean, values["latency_ms"]),
                "median": safe_stat(statistics.median, values["latency_ms"]),
                "min": safe_stat(min, values["latency_ms"]),
                "max": safe_stat(max, values["latency_ms"]),
                "p95": (
                    statistics.quantiles(values["latency_ms"], n=20)[18]
                    if len(values["latency_ms"]) > 1
                    else (values["latency_ms"][0] if values["latency_ms"] else 0.0)
                ),
            },
        }
    return aggregated


def overall_summary(metrics: list[dict]) -> dict:
    """Compute overall summary across all k values."""
    all_recall = [m["recall_at_k"] for m in metrics]
    all_precision = [m["precision_at_k"] for m in metrics]
    all_mrr = [m.get("mrr_at_k", 0.0) for m in metrics]
    all_latency = [m["latency_ms"] for m in metrics]

    def safe_stat(f, arr, default=0.0):
        try:
            return f(arr) if arr else default
        except Exception:
            return default

    return {
        "total_evaluations": len(metrics),
        "avg_recall": safe_stat(statistics.mean, all_recall),
        "avg_precision": safe_stat(statistics.mean, all_precision),
        "avg_mrr": safe_stat(statistics.mean, all_mrr),
        "avg_latency_ms": safe_stat(statistics.mean, all_latency),
        "median_recall": safe_stat(statistics.median, all_recall),
        "median_precision": safe_stat(statistics.median, all_precision),
        "median_latency_ms": safe_stat(statistics.median, all_latency),
    }


def main() -> None:
    script_dir = Path(__file__).parent
    cache_dir = script_dir / ".eval_cache"
    output_file = script_dir / "eval_report.json"

    if not cache_dir.exists():
        print(f"Error: Cache directory not found: {cache_dir}")
        print("Run eval tests first: uv run pytest -m eval")
        return

    print(f"Loading metrics from {cache_dir}...")
    metrics = load_all_cached_metrics(cache_dir)

    if not metrics:
        print("No cached metrics found. Run eval tests first.")
        return

    print(f"Found {len(metrics)} cached evaluations")

    print("Aggregating by k value...")
    by_k = aggregate_by_k(metrics)

    print("Computing overall summary...")
    summary = overall_summary(metrics)

    report = {
        "summary": summary,
        "by_k": by_k,
        "cache_location": str(cache_dir.absolute()),
        "report_generated_at": str(Path.cwd()),
    }

    print(f"Writing report to {output_file}...")
    with output_file.open("w") as f:
        json.dump(report, f, indent=2)

    print("\n✓ Report generated successfully!")
    print("\n📊 Summary:")
    print(f"  Total evaluations: {summary['total_evaluations']}")
    print(f"  Average recall: {summary['avg_recall']:.2%}")
    print(f"  Average precision: {summary['avg_precision']:.2%}")
    print(f"  Average latency: {summary['avg_latency_ms']:.2f}ms")
    print(f"\n📁 Full report: {output_file}")


if __name__ == "__main__":
    main()
