# pragma: no cover
import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ID_PATTERN = re.compile(r"^([A-Z0-9]+)\.([A-Z0-9]+)(?:\.([A-Z0-9]+))?$", re.IGNORECASE)


def _segment_sort_key(s: str) -> tuple[int, str | int]:
    """Sort numerically if digit-only, otherwise alphabetically after all numbers."""
    return (0, int(s)) if s.isdigit() else (1, s.upper())


def parse_entity_id(entity_id: str) -> tuple[str, ...] | None:
    match = ID_PATTERN.fullmatch(entity_id.strip())
    if not match:
        return None
    return tuple(part for part in match.groups() if part is not None)


def collect_ids_by_type(
    chunks: list[dict[str, Any]],
) -> tuple[dict[str, list[tuple[str, ...]]], list[dict[str, Any]]]:
    ids_by_type: dict[str, list[tuple[str, ...]]] = {}
    invalid_rows: list[dict[str, Any]] = []

    for chunk in chunks:
        chunk_type = chunk.get("chunk_type")
        if not chunk_type:
            continue

        if chunk_type not in ids_by_type:
            ids_by_type[chunk_type] = []

        entity_id = chunk.get("entity_id")
        if not entity_id:
            if chunk_type == "text":
                continue

            invalid_rows.append(
                {
                    "chunk_id": chunk.get("chunk_id"),
                    "chunk_type": chunk_type,
                    "entity_id": entity_id,
                    "reason": "missing entity_id",
                }
            )
            continue

        parsed = parse_entity_id(str(entity_id))
        if parsed is None:
            if chunk_type == "text":
                continue

            invalid_rows.append(
                {
                    "chunk_id": chunk.get("chunk_id"),
                    "chunk_type": chunk_type,
                    "entity_id": entity_id,
                    "reason": "invalid format, expected x.x or x.x.x",
                }
            )
            continue

        ids_by_type[chunk_type].append(parsed)

    return ids_by_type, invalid_rows


def _sort_key(parts: tuple[str, ...]) -> tuple[tuple[int, str | int], ...]:
    return tuple(_segment_sort_key(s) for s in parts)


def detect_gaps(ids: list[tuple[str, ...]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, ...], set[str]] = defaultdict(set)
    for parts in ids:
        parent = parts[:-1]
        grouped[parent].add(parts[-1])

    gaps: list[dict[str, Any]] = []
    for parent, tail_values in grouped.items():
        # Only detect gaps when all tail values are numeric
        if not all(v.isdigit() for v in tail_values):
            continue

        ordered = sorted(tail_values, key=lambda v: int(v))
        if not ordered:
            continue

        # Check if numbering starts at 1
        first_val = int(ordered[0])
        if first_val > 1:
            missing = [".".join((*parent, str(value))) for value in range(1, first_val)]
            gaps.append(
                {
                    "parent": ".".join(parent) if parent else "",
                    "after": "start",
                    "before": ".".join((*parent, ordered[0])),
                    "missing": missing,
                }
            )

        for current, nxt in zip(ordered, ordered[1:], strict=False):
            c, n = int(current), int(nxt)
            if n > c + 1:
                missing = [".".join((*parent, str(value))) for value in range(c + 1, n)]
                gaps.append(
                    {
                        "parent": ".".join(parent) if parent else "",
                        "after": ".".join((*parent, current)),
                        "before": ".".join((*parent, nxt)),
                        "missing": missing,
                    }
                )
    return gaps


def analyze(chunks: list[dict[str, Any]]) -> dict[str, Any]:
    ids_by_type, invalid_rows = collect_ids_by_type(chunks)

    report: dict[str, Any] = {"chunk_types": {}, "invalid_rows": invalid_rows}
    for chunk_type in sorted(ids_by_type):
        unique_sorted_ids = sorted(set(ids_by_type[chunk_type]), key=_sort_key)
        gaps = detect_gaps(unique_sorted_ids)

        report["chunk_types"][chunk_type] = {
            "count": len(unique_sorted_ids),
            "ids": [".".join(parts) for parts in unique_sorted_ids],
            "gaps": gaps,
        }

    return report


def print_report(report: dict[str, Any]) -> None:
    chunk_types = report["chunk_types"]
    if not chunk_types:
        print("No chunk entity IDs found.")
        return

    for chunk_type, info in chunk_types.items():
        print(f"\n[{chunk_type}] count={info['count']}")
        print("IDs:", ", ".join(info["ids"]) if info["ids"] else "-")

        counts = Counter(info["ids"])
        duplicates = [item for item, cnt in counts.items() if cnt > 1]

        print("Duplicate IDs:", ", ".join(duplicates) if duplicates else "-")

        if info["gaps"]:
            print("Missing IDs:")
            for gap in info["gaps"]:
                print(
                    f"  - between {gap['after']} and {gap['before']}: {', '.join(gap['missing'])}"
                )
        elif chunk_type != "text":
            print("Missing IDs: none")

    invalid_rows = report.get("invalid_rows", [])
    if invalid_rows:
        print(f"\nInvalid/missing entity_id rows: {len(invalid_rows)}")
        for row in invalid_rows:
            print(
                f"  - chunk_id={row['chunk_id']} type={row['chunk_type']} "
                f"entity_id={row['entity_id']} ({row['reason']})"
            )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Group chunks by chunk_type, sort entity_id values "
            "(x.x or x.x.x), and report missing IDs."
        )
    )
    parser.add_argument("file_path", type=Path, help="Path to chunks JSON")
    parser.add_argument(
        "--output-json",
        type=Path,
        help="Optional path to save machine-readable report",
    )
    args = parser.parse_args()

    with args.file_path.open() as f:
        chunks = json.load(f)

    report = analyze(chunks)
    print_report(report)

    if args.output_json:
        with args.output_json.open("w") as f:
            json.dump(report, f, indent=2)
        print(f"\nSaved report to {args.output_json}")


if __name__ == "__main__":
    main()
