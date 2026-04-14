# pragma: no cover
import argparse
import json
import re
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path
from typing import Any

SEGMENT_PATTERN = re.compile(r"[A-Za-z]+|\d+")


def _segment_sort_key(s: str) -> tuple[int, str | int]:
    """Numbers first (numeric order), then strings (lexicographic)."""
    return (0, int(s)) if s.isdigit() else (1, s.upper())


def _parse_number(value: str) -> tuple[str, ...] | None:
    """Parse 'A.10', '3.2', 'F.14' -> ('A','10'), ('3','2'), ..."""
    if not value or not isinstance(value, str):
        return None

    parts = value.strip().split(".")
    parsed: list[str] = []

    for part in parts:
        tokens = SEGMENT_PATTERN.findall(part)
        if not tokens:
            return None
        parsed.extend(tokens)

    return tuple(parsed)


def _sort_key(parts: tuple[str, ...]) -> tuple[tuple[int, str | int], ...]:
    return tuple(_segment_sort_key(p) for p in parts)


def _detect_gaps(values: Iterable[str]) -> list[dict[str, Any]]:
    parsed = [p for v in values if (p := _parse_number(v)) is not None]

    grouped: dict[tuple[str, ...], set[str]] = defaultdict(set)

    for parts in parsed:
        parent = parts[:-1]
        grouped[parent].add(parts[-1])

    gaps: list[dict[str, Any]] = []

    for parent, tails in grouped.items():
        # only numeric tails → gap detection possible
        if not all(t.isdigit() for t in tails):
            continue

        ordered = sorted(tails, key=lambda x: int(x))
        if not ordered:
            continue

        # Check if numbering starts at 1
        first_val = int(ordered[0])
        if first_val > 1:
            missing = [".".join((*parent, str(i))) for i in range(1, first_val)]
            gaps.append(
                {
                    "parent": ".".join(parent),
                    "after": "start",
                    "before": ".".join((*parent, ordered[0])),
                    "missing": missing,
                }
            )

        for a, b in zip(ordered, ordered[1:], strict=False):
            ai, bi = int(a), int(b)
            if bi > ai + 1:
                missing = [".".join((*parent, str(i))) for i in range(ai + 1, bi)]
                gaps.append(
                    {
                        "parent": ".".join(parent),
                        "after": ".".join((*parent, a)),
                        "before": ".".join((*parent, b)),
                        "missing": missing,
                    }
                )

    return gaps


def analyze(chunks: list[dict[str, Any]]) -> dict[str, Any]:
    part_titles = set()
    parts = set()

    section_titles = set()
    section_numbers = set()

    subsection_titles = set()
    subsection_numbers = set()

    subsubsection_titles = set()
    subsubsection_numbers = set()

    missing_titles: list[dict[str, Any]] = []
    hierarchy_issues: list[dict[str, Any]] = []

    for chunk in chunks:
        if chunk.get("part_title"):
            part_titles.add(chunk["part_title"])
        if chunk.get("part"):
            parts.add(chunk["part"])

        if chunk.get("section_title"):
            section_titles.add(chunk["section_title"])
        if chunk.get("section_number"):
            section_numbers.add(chunk["section_number"])

        if chunk.get("subsection_title"):
            subsection_titles.add(chunk["subsection_title"])
        if chunk.get("subsection_number"):
            subsection_numbers.add(chunk["subsection_number"])

        if chunk.get("subsubsection_title"):
            subsubsection_titles.add(chunk["subsubsection_title"])
        if chunk.get("subsubsection_number"):
            subsubsection_numbers.add(chunk["subsubsection_number"])

        # ---- missing titles ----
        cid = chunk.get("chunk_id")
        if chunk.get("section_number") and not chunk.get("section_title"):
            missing_titles.append(
                {
                    "chunk_id": cid,
                    "level": "section",
                    "number": chunk.get("section_number"),
                }
            )

        if chunk.get("subsection_number") and not chunk.get("subsection_title"):
            missing_titles.append(
                {
                    "chunk_id": cid,
                    "level": "subsection",
                    "number": chunk.get("subsection_number"),
                }
            )

        if chunk.get("subsubsection_number") and not chunk.get("subsubsection_title"):
            missing_titles.append(
                {
                    "chunk_id": cid,
                    "level": "subsubsection",
                    "number": chunk.get("subsubsection_number"),
                }
            )

        # ---- hierarchy validation ----
        if chunk.get("subsection_number") and not chunk.get("section_number"):
            hierarchy_issues.append(
                {
                    "chunk_id": cid,
                    "issue": "subsection without section",
                    "subsection": chunk.get("subsection_number"),
                }
            )

        if chunk.get("subsubsection_number") and not chunk.get("subsection_number"):
            hierarchy_issues.append(
                {
                    "chunk_id": cid,
                    "issue": "subsubsection without subsection",
                    "subsubsection": chunk.get("subsubsection_number"),
                }
            )

    def process_numbers(values: set[str]) -> dict[str, Any]:
        parsed = [(v, _parse_number(v)) for v in values if _parse_number(v) is not None]

        sorted_values = [
            v for v, _ in sorted(parsed, key=lambda x: _sort_key(x[1]))  # type: ignore
        ]

        gaps = _detect_gaps(values)

        return {
            "count": len(values),
            "values": sorted_values,
            "gaps": gaps,
        }

    return {
        "parts": sorted(parts),
        "part_titles": sorted(part_titles),
        "section_titles": sorted(section_titles),
        "subsection_titles": sorted(subsection_titles),
        "subsubsection_titles": sorted(subsubsection_titles),
        "section_numbers": process_numbers(section_numbers),
        "subsection_numbers": process_numbers(subsection_numbers),
        "subsubsection_numbers": process_numbers(subsubsection_numbers),
        "missing_titles": missing_titles,
        "hierarchy_issues": hierarchy_issues,
    }


def print_report(report: dict[str, Any]) -> None:
    print("\n[PARTS]")
    print(", ".join(report["parts"]) if report["parts"] else "-")

    print("\n[PART TITLES]")
    print("\n".join(report["part_titles"]) if report["part_titles"] else "-")

    print("\n[SECTION TITLES]")
    print("\n".join(report["section_titles"]) if report["section_titles"] else "-")

    print("\n[SUBSECTION TITLES]")
    print("\n".join(report["subsection_titles"]) if report["subsection_titles"] else "-")

    print("\n[SUBSUBSECTION TITLES]")
    print("\n".join(report["subsubsection_titles"]) if report["subsubsection_titles"] else "-")

    def print_numbers(name: str, data: dict[str, Any]) -> None:
        print(f"\n[{name}] count={data['count']}")
        print("Values:", ", ".join(data["values"]) if data["values"] else "-")

        if data["gaps"]:
            print("Missing:")
            for g in data["gaps"]:
                print(f"  - between {g['after']} and {g['before']}: {', '.join(g['missing'])}")
        else:
            print("Missing: none")

    print_numbers("SECTION NUMBERS", report["section_numbers"])
    print_numbers("SUBSECTION NUMBERS", report["subsection_numbers"])
    print_numbers("SUBSUBSECTION NUMBERS", report["subsubsection_numbers"])

    if report["missing_titles"]:
        print(f"\n[MISSING TITLES] count={len(report['missing_titles'])}")
        for row in report["missing_titles"]:
            print(f"  - chunk_id={row['chunk_id']} {row['level']} number={row['number']}")
    else:
        print("\n[MISSING TITLES] none")

    if report["hierarchy_issues"]:
        print(f"\n[HIERARCHY ISSUES] count={len(report['hierarchy_issues'])}")
        for row in report["hierarchy_issues"]:
            print(
                f"  - chunk_id={row['chunk_id']} {row['issue']} "
                f"{row.get('subsection') or row.get('subsubsection')}"
            )
    else:
        print("\n[HIERARCHY ISSUES] none")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyze titles and hierarchical numbering with gap detection."
    )
    parser.add_argument("file_path", type=Path)
    parser.add_argument("--output-json", type=Path)

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
