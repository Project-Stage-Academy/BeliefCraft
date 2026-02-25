import json
import re
from pathlib import Path
from typing import Any

import cv2  # type: ignore
import fitz  # type: ignore
import numpy as np
from common.logging import get_logger
from .config import (  # type: ignore
    BLOCK_KEYWORDS,
    CAPTION_KEYWORDS,
    DPI_RENDER,
    FIGURES_PDF,
    MAIN_PDF,
)
from tqdm import tqdm  # type: ignore

logger = get_logger(__name__)

# Local geometric constants
SIMILARITY_THRESHOLD = 0.8
CAPTION_OFFSET_X_MINUS = 5
CAPTION_OFFSET_X_PLUS = 100
CAPTION_HEIGHT = 60
SIDE_NOTE_WIDTH = 200
BLOCK_CONTENT_PADDING = 20


def get_scale_factor(dpi: int) -> float:
    """Calculates scale factor based on rendering DPI."""
    return 72.0 / dpi


def pdf_page_to_img(doc: Any, page_number: int, dpi: int = DPI_RENDER) -> Any:
    """
    Render a PDF page into an OpenCV-compatible image.
    """
    page = doc.load_page(page_number)
    pix = page.get_pixmap(dpi=dpi)

    img = np.frombuffer(pix.samples, dtype=np.uint8)
    img = img.reshape(pix.height, pix.width, pix.n)

    if pix.n == 4:
        img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
    else:
        img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)

    return img


def get_advanced_caption(
    page: Any, rect_coords: tuple[int, int, int, int], dpi: int = DPI_RENDER
) -> str:
    """
    Detect caption or block content associated with an image with strict pattern matching.
    """
    x, y, w, h = rect_coords
    scale = get_scale_factor(dpi)

    img_rect = fitz.Rect(x * scale, y * scale, (x + w) * scale, (y + h) * scale)

    blocks = page.get_text("blocks")

    caption_area = fitz.Rect(
        img_rect.x0 - CAPTION_OFFSET_X_MINUS,
        img_rect.y1,
        img_rect.x1 + CAPTION_OFFSET_X_PLUS,
        img_rect.y1 + CAPTION_HEIGHT,
    )

    side_area = fitz.Rect(img_rect.x1, img_rect.y0, img_rect.x1 + SIDE_NOTE_WIDTH, img_rect.y1)

    # 1. Strict Caption detection
    for b in blocks:
        block_rect = fitz.Rect(b[:4])
        text = b[4].strip()

        if (
            any(word in text.lower() for word in CAPTION_KEYWORDS)
            and re.search(r"(figure|table|algorithm)\s+(?:\d+|[A-G])\.\d+", text, re.I)
            and (block_rect.intersects(caption_area) or block_rect.intersects(side_area))
        ):
            return str(text.replace("\n", " "))

    # 2. Block detection (example / exercise)
    candidate_header: Any | None = None
    header_type = ""

    for b in blocks:
        block_rect = fitz.Rect(b[:4])
        text = b[4].strip().lower()

        if any(word in text for word in BLOCK_KEYWORDS) and block_rect.y0 < img_rect.y1:
            candidate_header = block_rect
            header_type = "EXAMPLE" if "example" in text else "EXERCISE"

    if candidate_header:
        content_rect = fitz.Rect(
            candidate_header.x0,
            candidate_header.y0,
            page.rect.width,
            img_rect.y1 + BLOCK_CONTENT_PADDING,
        )
        full_content = page.get_text("text", clip=content_rect).strip()
        return f"[BLOCK {header_type} CONTENT]:\n{full_content}"

    return "Image without specific caption or block header"


def process_pdf(
    dm_pdf_path: str | Path,
    figures_pdf_path: str | Path,
    output_json: str = "figures_metadata.json",
) -> None:
    """
    Detect figures in main PDF using template matching and
    extract metadata efficiently using buffered writes.
    """
    all_entries: list[dict[str, Any]] = []

    with fitz.open(dm_pdf_path) as dm_doc, fitz.open(figures_pdf_path) as figs_doc:
        already_found: set[int] = set()
        total_figs = len(figs_doc)

        logger.info(f"Processing {len(dm_doc)} pages against {total_figs} templates...")

        for page_num in tqdm(range(len(dm_doc)), desc="Searching images"):
            page_img = pdf_page_to_img(dm_doc, page_num)
            page_obj = dm_doc.load_page(page_num)
            page_gray = cv2.cvtColor(page_img, cv2.COLOR_BGR2GRAY)

            for idx in range(total_figs):
                if idx in already_found:
                    continue

                template = pdf_page_to_img(figs_doc, idx)
                template_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)

                t_h, t_w = template.shape[:2]
                p_h, p_w = page_img.shape[:2]

                if t_h <= p_h and t_w <= p_w:
                    res = cv2.matchTemplate(page_gray, template_gray, cv2.TM_CCOEFF_NORMED)
                    _, max_val, _, max_loc = cv2.minMaxLoc(res)

                    if max_val >= SIMILARITY_THRESHOLD:
                        description = get_advanced_caption(
                            page_obj, (max_loc[0], max_loc[1], t_w, t_h), dpi=DPI_RENDER
                        )

                        img_type = "captioned_image"
                        if "[BLOCK EXAMPLE" in description:
                            img_type = "example"
                        elif "[BLOCK EXERCISE" in description:
                            img_type = "exercise"

                        decimal_match = re.search(r"((?:\d+|[A-G])\.\d+)", description)
                        integer_match = re.search(r"(\d+)", description)

                        entity_id = (
                            decimal_match.group(1)
                            if decimal_match
                            else integer_match.group(1) if integer_match else None
                        )

                        entry = {
                            "chunk_type": img_type,
                            "entity_id": entity_id,
                            "page": page_num + 1,
                            "image_index": idx + 1,
                            "content": description,
                            "similarity": round(float(max_val), 4),
                            "bbox": [
                                float(max_loc[0]),
                                float(max_loc[1]),
                                float(max_loc[0] + t_w),
                                float(max_loc[1] + t_h),
                            ],
                        }

                        all_entries.append(entry)
                        already_found.add(idx)

    try:
        output_path = Path(output_json)
        with output_path.open("w", encoding="utf-8") as f:
            json.dump(all_entries, f, indent=2, ensure_ascii=False)
        logger.info(f"Successfully saved {len(all_entries)} entries to {output_json}")
    except OSError as e:
        logger.error(f"Failed to write results to {output_json}: {e}")


if __name__ == "__main__":
    process_pdf(MAIN_PDF, FIGURES_PDF)
