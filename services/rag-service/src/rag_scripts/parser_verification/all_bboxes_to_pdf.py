# pragma: no cover
import argparse
import json
import re
from pathlib import Path
from typing import Any

import fitz  # type: ignore


def load_rows(path: Path) -> list[dict[str, Any]]:
    """Loads a list of rows from a JSON file, handling various common structures.

    Args:
        path: Path to the JSON file.

    Returns:
        A list of dictionaries representing the data rows.

    Raises:
        ValueError: If the JSON structure is not a list or doesn't contain a known data key.
    """
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, list):
        return data

    if isinstance(data, dict):
        for key in ("chunks", "items", "results", "data"):
            val = data.get(key)
            if isinstance(val, list):
                return val

    raise ValueError(f"Invalid JSON structure in {path}")


def load_paddle_dir(directory: Path) -> list[dict[str, Any]]:
    """Loads all JSON files from a directory, typically from PaddleOCR output.

    Args:
        directory: The directory containing JSON files.

    Returns:
        A combined list of all rows from all JSON files in the directory.
    """
    rows: list[dict[str, Any]] = []

    if not directory.exists():
        return rows

    files = sorted(
        [f for f in directory.iterdir() if f.suffix == ".json"],
        key=lambda f: [int(s) if s.isdigit() else s for s in re.split(r"(\d+)", f.name)],
    )

    for fpath in files:
        with fpath.open("r", encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, list):
            rows.extend(data)
        elif isinstance(data, dict):
            rows.append(data)

    return rows


def extract_paddle_boxes(pages: list[dict[str, Any]]) -> list[tuple[int, list[float], int]]:
    """Extracts bounding boxes from PaddleOCR JSON output pages.

    Args:
        pages: A list of page data dictionaries.

    Returns:
        A list of tuples containing (page_index, bounding_box, block_id).
    """
    result: list[tuple[int, list[float], int]] = []

    for i, page in enumerate(pages):
        page_num = page.get("page_num", i + 1)

        blocks = page.get("prunedResult", {}).get("parsing_res_list", [])
        if not isinstance(blocks, list):
            continue

        for block in blocks:
            bbox = block.get("block_bbox")
            if not isinstance(bbox, list) or len(bbox) != 4:
                continue

            result.append((page_num - 1, [float(x) for x in bbox], block["block_id"]))

    return result


def rect_from_pixels(bbox: list[float], dpi: float) -> list[float]:
    """Converts a bounding box from pixels to PDF points using the provided DPI.

    Args:
        bbox: The bounding box in pixels [x1, y1, x2, y2].
        dpi: The dots per inch of the source image.

    Returns:
        The bounding box in PDF points.
    """
    x1, y1, x2, y2 = bbox
    scale = 72.0 / dpi
    return [x1 * scale, y1 * scale, x2 * scale, y2 * scale]


def rect_paddle(
    bbox: list[float], page: fitz.Page, w_paddle: float, h_paddle: float
) -> list[float]:
    """Scales a PaddleOCR bounding box to the dimensions of a fitz.Page.

    Args:
        bbox: The bounding box in PaddleOCR coordinate space.
        page: The target fitz.Page object.
        w_paddle: The reference width used by PaddleOCR.
        h_paddle: The reference height used by PaddleOCR.

    Returns:
        The scaled bounding box in PDF points.
    """
    x1, y1, x2, y2 = bbox

    w_fitz = page.rect.width
    h_fitz = page.rect.height

    x1 = x1 / w_paddle * w_fitz
    x2 = x2 / w_paddle * w_fitz
    y1 = y1 / h_paddle * h_fitz
    y2 = y2 / h_paddle * h_fitz

    return [x1, y1, x2, y2]


def draw_rect(
    page: fitz.Page, bbox: list[float], color: tuple[float, float, float], label: str | None = None
) -> None:
    """Draws a rectangle on a fitz.Page.

    Args:
        page: The page to draw on.
        bbox: The bounding box [x1, y1, x2, y2].
        color: The color of the rectangle as an (R, G, B) tuple.
    """
    rect = fitz.Rect(
        min(bbox[0], bbox[2]),
        min(bbox[1], bbox[3]),
        max(bbox[0], bbox[2]),
        max(bbox[1], bbox[3]),
    )

    page.draw_rect(rect, color=color, width=1.2)

    if label:
        text_position = fitz.Point(rect.x0, rect.y0 - 1)

        page.insert_text(
            text_position,
            label,
            fontsize=8,
            color=color,
        )


def load_chunks(path: Path) -> list[dict[str, Any]]:
    """Loads the chunks JSON.

    Args:
        path: Path to the JSON file.

    Returns:
        A list of chunk dictionaries.
    """
    if not path.exists():
        return []

    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, list):
        return data
    return []


def get_chunk_id_by_block_id(chunks: list[dict[str, Any]], block_id: str) -> str | None:
    """Return the chunk_id that contains the given pdf block_id"""
    for chunk in chunks:
        pdf_block_ids = chunk.get("pdf_block_ids")
        if not isinstance(pdf_block_ids, list):
            continue
        if block_id in pdf_block_ids:
            return str(chunk["chunk_id"])
    return None


def main() -> None:
    """Main entry point for the script."""
    parser = argparse.ArgumentParser()

    parser.add_argument("input_pdf", type=Path)
    parser.add_argument("blocks_json", type=Path)
    parser.add_argument("images_json", type=Path)
    parser.add_argument("paddle_dir", type=Path)
    parser.add_argument("--input_json", type=Path)

    parser.add_argument("-o", "--output", type=Path, default=Path("out.pdf"))
    parser.add_argument("--dpi", type=float, default=200.0)

    parser.add_argument("--paddle-width", type=float, default=1152.0)
    parser.add_argument("--paddle-height", type=float, default=1296.0)

    args = parser.parse_args()

    doc = fitz.open(str(args.input_pdf))

    blocks = load_rows(args.blocks_json)
    images = load_rows(args.images_json)
    paddle_pages = load_paddle_dir(args.paddle_dir)
    paddle_boxes = extract_paddle_boxes(paddle_pages)

    if args.input_json:
        chunks = load_chunks(args.input_json)
        print("Loaded", len(chunks), "chunks from", args.input_json)
    else:
        chunks = None

    # blocks (already in PDF points)
    for row in blocks:
        bbox = row.get("bbox") or row.get("box") or row.get("points")
        page_num = row.get("page", 1) - 1

        if not bbox or len(bbox) != 4:
            continue
        if page_num < 0 or page_num >= len(doc):
            continue

        page = doc.load_page(page_num)
        draw_rect(page, bbox, (1, 0, 0))

    # images (in pixels, need scaling)
    for row in images:
        bbox = row.get("bbox") or row.get("box") or row.get("points")
        page_num = row.get("page", 1) - 1

        if not bbox or len(bbox) != 4:
            continue
        if page_num < 0 or page_num >= len(doc):
            continue

        page = doc.load_page(page_num)
        b = rect_from_pixels(bbox, args.dpi)
        draw_rect(page, b, (0, 1, 0))

    # paddle
    for page_num, bbox, page_block_id in paddle_boxes:
        if page_num < 0 or page_num >= len(doc):
            continue

        page = doc.load_page(page_num)
        b = rect_paddle(
            bbox,
            page,
            args.paddle_width,
            args.paddle_height,
        )
        if chunks:
            chunk_id = get_chunk_id_by_block_id(chunks, f"{page_num + 1}:{page_block_id}")
            label = f"{page_block_id}  {chunk_id if chunk_id else ''}"
        else:
            label = str(page_block_id)
        draw_rect(page, b, (0, 0, 1), label=label)

    doc.save(str(args.output))
    doc.close()

    print(f"Saved to {args.output}")


if __name__ == "__main__":
    main()
