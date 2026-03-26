# pragma: no cover
import argparse
import json
from pathlib import Path
from typing import Any


def collect_referenced_values(chunks: list[dict[str, Any]]) -> dict[str, set[str]]:
    """Collect unique values for all fields starting with 'referenced_'."""
    referenced_values: dict[str, set[str]] = {}
    for chunk in chunks:
        for key, value in chunk.items():
            if key.startswith("referenced_"):
                if key not in referenced_values:
                    referenced_values[key] = set()

                if isinstance(value, list):
                    for item in value:
                        if item is not None and item != "":
                            referenced_values[key].add(str(item))
                elif value is not None and value != "":
                    referenced_values[key].add(str(value))
    return referenced_values


def reference_sort_key(s: str) -> list[tuple[int, Any]]:
    """
    Sort key for hierarchical references like '1.2.3' or 'A.1'.
    Splits by dots and prioritizes digits over letters at each level.
    """
    parts = s.split(".")
    key: list[tuple[int, Any]] = []
    for p in parts:
        if p.isdigit():
            # (0, int) -> Digits first (type 0), then numeric sort
            key.append((0, int(p)))
        else:
            # (1, str) -> Letters second (type 1), then alphabetic sort
            key.append((1, p))
    return key


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Print unique values for all 'referenced_' fields in chunks JSON."
    )
    parser.add_argument("file_path", help="Path to the JSON file containing chunks.", type=Path)
    parser.add_argument(
        "--output",
        help="Path to the output JSON file. If provided, writes results to this file.",
        type=Path,
    )
    args = parser.parse_args()

    try:
        with args.file_path.open() as f:
            chunks = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Failed to load JSON file: {e}")
        return

    referenced_data = collect_referenced_values(chunks)

    if not referenced_data:
        print("No fields starting with 'referenced_' found.")
        return

    # Convert sets to sorted lists for stable output using custom hierarchical key
    output = {
        key: sorted(values, key=reference_sort_key)
        for key, values in sorted(referenced_data.items())
    }

    if args.output:
        print(f"Writing results to {args.output}")
        with args.output.open("w") as f:
            json.dump(output, f, indent=2)
    else:
        for key, values in output.items():
            print(f"{key}: {', '.join(values)}")


if __name__ == "__main__":
    main()
