# pragma: no cover
import argparse
import json
from collections import defaultdict
from pathlib import Path

import fitz  # type: ignore[import-untyped]
from pydantic import BaseModel, ValidationError


class ChunkBBox(BaseModel):
    chunk_type: str | None = None
    entity_id: str | None = None
    chunk_id: str | None = None
    page: int
    bbox: list[float]


def _build_label(chunk: ChunkBBox) -> str:
    if chunk.chunk_id:
        return chunk.chunk_id
    if chunk.entity_id and chunk.chunk_type:
        return f"{chunk.chunk_type}:{chunk.entity_id}"
    if chunk.entity_id:
        return chunk.entity_id
    return chunk.chunk_type or "chunk"


def _load_chunks(input_json: Path) -> list[ChunkBBox]:
    with input_json.open("r", encoding="utf-8") as f:
        raw = json.load(f)

    if isinstance(raw, list):
        rows = raw
    elif isinstance(raw, dict):
        for key in ("chunks", "items", "results", "data"):
            value = raw.get(key)
            if isinstance(value, list):
                rows = value
                break
        else:
            raise ValueError(
                "JSON must be a list or include a list under one of: chunks, items, results, data"
            )
    else:
        raise ValueError("JSON root must be a list or object")

    parsed: list[ChunkBBox] = []
    skipped = 0

    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            skipped += 1
            print(f"Skipping row {index}: expected object, got {type(row).__name__}")
            continue
        try:
            parsed.append(ChunkBBox.model_validate(row))
        except ValidationError as exc:
            skipped += 1
            print(f"Skipping row {index}: {exc.errors()[0]['msg']}")

    print(f"Loaded {len(parsed)} chunks from {input_json}")
    if skipped:
        print(f"Skipped {skipped} invalid rows")
    return parsed


def _get_page_index(chunk_page: int, page_base: int) -> int:
    return chunk_page - 1 if page_base == 1 else chunk_page


def _to_pdf_rect(
    bbox: list[float],
    bbox_space: str,
    bbox_dpi: float,
) -> fitz.Rect:
    x0, y0, x1, y1 = bbox
    if bbox_space == "pixel":
        scale = 72.0 / bbox_dpi
        x0, y0, x1, y1 = x0 * scale, y0 * scale, x1 * scale, y1 * scale
    return fitz.Rect(min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))


def render_bboxes_to_pdf(
    input_pdf: Path,
    input_json: Path,
    output_pdf: Path,
    page_base: int,
    stroke_width: float,
    bbox_space: str,
    bbox_dpi: float,
) -> None:
    chunks = _load_chunks(input_json)
    by_page: dict[int, list[ChunkBBox]] = defaultdict(list)

    for chunk in chunks:
        by_page[_get_page_index(chunk.page, page_base)].append(chunk)

    doc = fitz.open(str(input_pdf))
    drawn = 0
    skipped = 0

    for page_index, page_chunks in sorted(by_page.items()):
        if page_index < 0 or page_index >= len(doc):
            skipped += len(page_chunks)
            print(f"Skipping {len(page_chunks)} chunks: page {page_index} out of range")
            continue

        page = doc.load_page(page_index)

        for chunk in page_chunks:
            if len(chunk.bbox) != 4:
                skipped += 1
                print(f"Skipping chunk with invalid bbox length on page {chunk.page}: {chunk.bbox}")
                continue

            rect = _to_pdf_rect(chunk.bbox, bbox_space=bbox_space, bbox_dpi=bbox_dpi)
            page.draw_rect(rect, color=(1, 0, 0), width=stroke_width, overlay=True)

            label = _build_label(chunk)
            text_origin = fitz.Point(rect.x0, max(8.0, rect.y0 - 2.0))
            page.insert_text(
                text_origin,
                label,
                fontsize=8,
                color=(1, 0, 0),
                overlay=True,
            )
            drawn += 1

    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(output_pdf))
    doc.close()

    print(f"Drawn boxes: {drawn}")
    if skipped:
        print(f"Skipped boxes: {skipped}")
    print(f"Saved annotated PDF to {output_pdf}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Draw chunk bounding boxes from JSON onto PDF pages.",
    )
    parser.add_argument("input_json", type=Path, help="Path to JSON with chunk entries")
    parser.add_argument("input_pdf", type=Path, help="Path to source PDF")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("annotated_book.pdf"),
        help="Path for output annotated PDF",
    )
    parser.add_argument(
        "--page-base",
        type=int,
        choices=(0, 1),
        default=1,
        help="Interpret JSON page numbers as 0-based or 1-based (default: 1)",
    )
    parser.add_argument(
        "--stroke-width",
        type=float,
        default=1.5,
        help="Bounding box line width",
    )
    parser.add_argument(
        "--bbox-space",
        choices=("pixel", "point"),
        default="pixel",
        help=(
            "Coordinate space of JSON bbox values. "
            "Use 'pixel' for image_processor output (default), 'point' for PDF points."
        ),
    )
    parser.add_argument(
        "--bbox-dpi",
        type=float,
        default=200.0,
        help=(
            "DPI used when bbox-space is 'pixel'. image_processor uses 200 by default, "
            "so pixel bboxes are converted to PDF points with factor 72/dpi."
        ),
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    render_bboxes_to_pdf(
        input_pdf=args.input_pdf,
        input_json=args.input_json,
        output_pdf=args.output,
        page_base=args.page_base,
        stroke_width=args.stroke_width,
        bbox_space=args.bbox_space,
        bbox_dpi=args.bbox_dpi,
    )


if __name__ == "__main__":
    main()
