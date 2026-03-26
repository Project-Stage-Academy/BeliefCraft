"""
Combinatorial test suite generator for RAG retrieval evaluation.

From each RAGTestCase, generates three ScenarioVariant instances:
- baseline: No filters, pure semantic search
- filtered: Correct metadata filters matching expected chunks
- contradictory: Mismatched filters → expect_empty=True

Also generates retrieval_coverage.md report (via --report flag).
"""

import argparse
import sys
from pathlib import Path
from typing import Any

import weaviate
from common.logging import configure_logging, get_logger
from rag_service.models import SearchFilters
from weaviate.classes.query import Filter

from .golden_set import load_golden_set
from .models import RAGTestCase, ScenarioVariant

logger = get_logger(__name__)


def fetch_chunk_metadata(
    client: weaviate.WeaviateClient, chunk_ids: list[str], collection_name: str
) -> dict[str, dict[str, Any]]:
    """Fetch metadata for a list of chunk UUIDs from Weaviate using BATCH query.

    Args:
        client: Weaviate client instance.
        chunk_ids: List of Weaviate UUIDs.
        collection_name: Weaviate collection name.

    Returns:
        Dict mapping UUID (str) → metadata dict.
    """
    collection = client.collections.use(collection_name)
    metadata_map: dict[str, dict[str, Any]] = {}

    try:
        response = collection.query.fetch_objects(
            filters=Filter.by_id().contains_any(chunk_ids),
            return_properties=["part", "section_number", "subsection_number", "page"],
            limit=len(chunk_ids),
        )

        for obj in response.objects:
            if obj.properties:
                metadata_map[str(obj.uuid)] = dict(obj.properties)

        if len(metadata_map) < len(chunk_ids):
            missing = set(chunk_ids) - set(metadata_map.keys())
            logger.warning("some_chunks_not_found_in_weaviate", missing_count=len(missing))

    except Exception as exc:
        logger.error("chunk_metadata_batch_fetch_failed", error=str(exc))

    return metadata_map


def generate_baseline_variant() -> ScenarioVariant:
    """Generate baseline scenario: no filters."""
    return ScenarioVariant(
        variant="baseline",
        filters=None,
        expect_empty=False,
        latency_budget_ms=1000,
    )


def generate_filtered_variants(metadata_map: dict[str, dict[str, Any]]) -> list[ScenarioVariant]:
    """Generate filtered scenarios from chunk metadata.

    Creates one variant per unique filter combination found in metadata.

    Args:
        metadata_map: Dict mapping chunk UUID → metadata.

    Returns:
        List of filtered ScenarioVariant instances.
    """
    variants: list[ScenarioVariant] = []
    seen_filters: set[tuple] = set()

    for metadata in metadata_map.values():
        part = metadata.get("part")
        section = metadata.get("section_number")
        subsection = metadata.get("subsection_number")
        page = metadata.get("page")

        filter_tuple = (part, section, subsection, page)
        if filter_tuple in seen_filters:
            continue
        seen_filters.add(filter_tuple)

        filters = SearchFilters(
            part=part,
            section=section,
            subsection=subsection,
            page_number=page,
        )

        variants.append(
            ScenarioVariant(
                variant="filtered",
                filters=filters,
                expect_empty=False,
                latency_budget_ms=1000,
            )
        )

    return variants


def generate_contradictory_variant(metadata_map: dict[str, dict[str, Any]]) -> ScenarioVariant:
    """Generate contradictory scenario: mismatched filter.

    Chooses a filter that does NOT match any chunk in metadata_map.

    Args:
        metadata_map: Dict mapping chunk UUID → metadata.

    Returns:
        Contradictory ScenarioVariant.
    """
    existing_parts = {m.get("part") for m in metadata_map.values() if m.get("part")}

    all_parts = ["I", "II", "III", "IV", "V", "Appendices"]
    contradictory_part = next((p for p in all_parts if p not in existing_parts), "V")

    return ScenarioVariant(
        variant="contradictory",
        filters=SearchFilters(part=contradictory_part),
        expect_empty=True,
        latency_budget_ms=1000,
    )


def generate_scenarios_for_case(
    case: RAGTestCase, metadata_map: dict[str, dict[str, Any]]
) -> list[ScenarioVariant]:
    """Generate all scenario variants for a single RAGTestCase.

    Args:
        case: The test case.
        metadata_map: Metadata for expected chunks.

    Returns:
        List of ScenarioVariant instances (baseline + filtered + contradictory).
    """
    scenarios: list[ScenarioVariant] = []

    scenarios.append(generate_baseline_variant())

    filtered = generate_filtered_variants(metadata_map)
    scenarios.extend(filtered)

    scenarios.append(generate_contradictory_variant(metadata_map))

    return scenarios


def generate_test_suite(
    golden_set_path: Path | None = None,
    collection_name: str = "unified_collection",
) -> list[RAGTestCase]:
    """Generate full test suite with scenario variants.

    Args:
        golden_set_path: Path to golden_set.json (None = default location).
        collection_name: Weaviate collection name.

    Returns:
        List of RAGTestCase instances with populated scenarios.
    """
    cases = load_golden_set(golden_set_path)

    try:
        with weaviate.connect_to_local(host="localhost", port=8080, grpc_port=50051) as client:
            for case in cases:
                metadata_map = fetch_chunk_metadata(
                    client, case.expected_chunk_ids, collection_name
                )

                if not metadata_map:
                    logger.warning("no_metadata_found", case_id=case.id)
                    continue

                case.scenarios = generate_scenarios_for_case(case, metadata_map)
                logger.info("scenarios_generated", case_id=case.id, count=len(case.scenarios))

    except weaviate.exceptions.WeaviateConnectionError as exc:
        logger.error("weaviate_connection_failed", error=str(exc))
        sys.exit(1)

    return cases


def generate_coverage_report(cases: list[RAGTestCase], output_path: Path) -> None:
    """Generate retrieval_coverage.md report.

    Args:
        cases: List of test cases with scenarios.
        output_path: Where to write the report.
    """
    lines = [
        "# RAG Retrieval Test Suite Coverage\n",
        f"\n**Total test cases:** {len(cases)}\n",
        f"**Validation split:** {sum(1 for c in cases if c.split == 'validation')}\n",
        f"**Test split:** {sum(1 for c in cases if c.split == 'test')}\n\n",
        "## Scenario Breakdown\n\n",
        "| Case ID | Baseline | Filtered | Contradictory | Total Scenarios |\n",
        "|---------|----------|----------|---------------|----------------|\n",
    ]

    for case in cases:
        baseline_count = sum(1 for s in case.scenarios if s.variant == "baseline")
        filtered_count = sum(1 for s in case.scenarios if s.variant == "filtered")
        contradictory_count = sum(1 for s in case.scenarios if s.variant == "contradictory")
        total = len(case.scenarios)

        lines.append(
            f"| {case.id}    | {baseline_count}     | {filtered_count}     "
            f"| {contradictory_count}       | {total}    |\n"
        )

    output_path.write_text("".join(lines), encoding="utf-8")
    logger.info("coverage_report_written", path=str(output_path))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate RAG retrieval test suite.")
    parser.add_argument(
        "--golden-set",
        type=Path,
        help="Path to golden_set.json (default: tests/retrieval/golden_set.json)",
    )
    parser.add_argument(
        "--report",
        type=Path,
        help="Generate coverage report at this path (e.g., retrieval_coverage.md)",
    )
    parser.add_argument(
        "--collection-name",
        default="unified_collection",
        help="Weaviate collection name (default: unified_collection)",
    )
    return parser.parse_args()


def main() -> None:
    configure_logging(service_name="generate-test-suite")
    args = parse_args()

    cases = generate_test_suite(args.golden_set, args.collection_name)

    logger.info("test_suite_generated", total_cases=len(cases))

    if args.report:
        generate_coverage_report(cases, args.report)


if __name__ == "__main__":
    main()
