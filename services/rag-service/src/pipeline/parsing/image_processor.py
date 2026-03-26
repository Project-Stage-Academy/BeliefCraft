import json
import re
from pathlib import Path
from typing import Any, cast

import cv2
import fitz  # type: ignore
import numpy as np
from common.logging import get_logger
from tqdm import tqdm  # type: ignore[import-untyped]

from .config import (
    DPI_RENDER,
    EXAMPLE_PATTERN,
    EXERCISE_PATTERN,
    FIGURE_PATTERN,
    FIGURES_PDF,
    MAIN_PDF,
)

logger = get_logger(__name__)

# Local geometric constants
SIMILARITY_THRESHOLD = 0.6
CAPTION_OFFSET_X_MINUS = 10
CAPTION_OFFSET_Y_MINUS = 50
CAPTION_OFFSET_X_PLUS = 150
CAPTION_HEIGHT = 30
SIDE_NOTE_WIDTH = 200
BLOCK_CONTENT_PADDING = 20

CAPTION_OFFSET_Y_MINUS_EXPANDED = 300
CAPTION_OFFSET_PLUS_X_EXPANDED = 800
CAPTION_HEIGHT_EXPANDED = 400

FIGURES_BBOX_OVERRIDE = {
    # image on page 267 of dm-figures.pdf contains empty space that confuses matching;
    # override manually
    266: ((242, 1040), 300, 327)
}

FIGURES_DESCRIPTION_BLOCKS = {
    594: (594, 2),
    595: (594, 2),
}

SKIP_COMBINATIONS = [  # Known difficult combinations of (fig_page_idx, dm_page_idx)
    (9, 48),
    (194, 348),
]

SCALES = np.concatenate(
    [[1.0, 1.05, 1.1], np.arange(1.0, 0.49, -0.01)]  # Different scales to try for template matching
)


def get_scale_factor(dpi: int) -> float:
    """Calculates scale factor based on rendering DPI."""
    return 72.0 / dpi


def pdf_page_to_img(doc: Any, page_number: int, dpi: int = DPI_RENDER) -> np.ndarray:
    """
    Render a PDF page into an OpenCV-compatible image.
    """
    page = doc.load_page(page_number)
    pix = page.get_pixmap(dpi=dpi)

    img = np.frombuffer(pix.samples, dtype=np.uint8)
    img = img.reshape(pix.height, pix.width, pix.n)

    if pix.n == 4:
        return cast(np.ndarray, cv2.cvtColor(img, cv2.COLOR_BGRA2BGR))
    return cast(np.ndarray, cv2.cvtColor(img, cv2.COLOR_RGB2BGR))


def get_page_exercise(page: Any) -> str | None:
    """Extract the latest exercise header/content snippet visible on a page."""
    blocks = page.get_text("blocks")
    for b in blocks[::-1]:
        block_rect = fitz.Rect(b[:4])
        text = b[4].strip()

        clean_text = text.replace("\n", " ")

        match = EXERCISE_PATTERN.search(clean_text)

        if match:
            candidate_header = block_rect
            full_content = page.get_text("text", clip=candidate_header).strip().replace("\n", " ")
            return str(full_content[match.start() :])
    return None


def _iter_caption_areas(img_rect: fitz.Rect) -> list[tuple[fitz.Rect, fitz.Rect]]:
    """Build candidate caption and side-note areas around an image rectangle."""
    areas: list[tuple[fitz.Rect, fitz.Rect]] = []
    for y_offset_minus, x_offset, y_offset in [
        (CAPTION_OFFSET_Y_MINUS, CAPTION_OFFSET_X_PLUS, CAPTION_HEIGHT),
        (CAPTION_OFFSET_Y_MINUS_EXPANDED, CAPTION_OFFSET_PLUS_X_EXPANDED, CAPTION_HEIGHT_EXPANDED),
    ]:
        caption_area = fitz.Rect(
            img_rect.x0 - CAPTION_OFFSET_X_MINUS,
            img_rect.y1 - y_offset_minus,
            img_rect.x1 + x_offset,
            img_rect.y1 + y_offset,
        )
        side_area = fitz.Rect(img_rect.x1, img_rect.y0, img_rect.x1 + SIDE_NOTE_WIDTH, img_rect.y1)
        areas.append((caption_area, side_area))
    return areas


def _find_strict_figure_caption(
    blocks: list[tuple[Any, ...]], caption_area: fitz.Rect, side_area: fitz.Rect
) -> str | None:
    """Find a figure-style caption in blocks intersecting caption or side-note regions."""
    for b in blocks[::-1]:
        block_rect = fitz.Rect(b[:4])
        text = b[4].strip()

        clean_text = text.replace("\n", " ")
        match = FIGURE_PATTERN.search(clean_text)

        if match and (block_rect.intersects(caption_area) or block_rect.intersects(side_area)):
            return str(clean_text[match.start() :])
    return None


def _find_block_content(
    page: Any, blocks: list[tuple[Any, ...]], img_rect: fitz.Rect
) -> str | None:
    """Return exercise/example block text associated with an image, when present."""
    for b in blocks[::-1]:
        block_rect = fitz.Rect(b[:4])
        text = b[4].strip()

        if block_rect.y0 < img_rect.y1:
            clean_text = text.replace("\n", " ")
            match = EXERCISE_PATTERN.search(clean_text) or EXAMPLE_PATTERN.search(clean_text)

            if match:
                content_rect = fitz.Rect(
                    block_rect.x0,
                    block_rect.y0,
                    page.rect.width,
                    img_rect.y1 + BLOCK_CONTENT_PADDING,
                )
                full_content = page.get_text("text", clip=content_rect).strip().replace("\n", " ")
                return str(full_content[match.start() :])
    return None


def get_advanced_caption(
    page: Any, prev_page: Any, rect_coords: tuple[float, float, float, float]
) -> str:
    """
    Detect caption or block content associated with an image.

    `rect_coords` must be in fitz page coordinates: (x0, y0, x1, y1).
    """
    img_rect = fitz.Rect(*rect_coords)
    blocks = page.get_text("blocks")

    for caption_area, side_area in _iter_caption_areas(img_rect):
        caption = _find_strict_figure_caption(blocks, caption_area, side_area)
        if caption:
            return caption

        block_content = _find_block_content(page, blocks, img_rect)
        if block_content:
            return block_content

    prev_page_exercise = get_page_exercise(prev_page)
    if prev_page_exercise:
        return prev_page_exercise

    return "Image without specific caption or block header"


def _match_template_on_page(
    page_gray: np.ndarray, template_gray: np.ndarray
) -> tuple[float, tuple[int, int], float] | None:
    """
    Multi-scale template matching using TM_CCOEFF_NORMED.
    Returns best similarity and location if a match is found.
    """
    p_h, p_w = page_gray.shape[:2]

    best_val = -1.0
    best_loc: tuple[int, int] | None = None
    best_scale = SCALES[0]

    for scale in SCALES:
        resized = cv2.resize(
            template_gray,
            None,
            fx=scale,
            fy=scale,
            interpolation=cv2.INTER_LINEAR,
        )

        t_h, t_w = resized.shape[:2]

        if t_h > p_h or t_w > p_w:
            continue

        res = cv2.matchTemplate(page_gray, resized, cv2.TM_CCOEFF_NORMED)
        min_v, max_val, min_l, max_l = cv2.minMaxLoc(res)
        max_loc = (int(max_l[0]), int(max_l[1]))

        if max_val > best_val:
            best_val = max_val
            best_loc = max_loc
            best_scale = scale

    logger.debug("Template match scale=%s similarity=%.4f", best_scale, best_val)
    if best_val >= SIMILARITY_THRESHOLD and best_loc is not None:
        return float(best_val), best_loc, best_scale

    return None


def _mask_matched_region(
    page_gray: np.ndarray, max_loc: tuple[int, int], t_w: int, t_h: int
) -> None:
    """Paint matched region white to avoid duplicate/near-duplicate matches later."""
    x0, y0 = max_loc
    x1 = min(x0 + t_w, page_gray.shape[1])
    y1 = min(y0 + t_h, page_gray.shape[0])

    if x0 < 0 or y0 < 0 or x0 >= x1 or y0 >= y1:
        return

    page_gray[y0:y1, x0:x1] = 255


def _create_entry(
    description: str,
    page_num: int,
    idx: int,
    max_val: float,
    max_loc: tuple[int, int],
    t_w: int,
    t_h: int,
) -> dict[str, Any]:
    """
    Encapsulates the logic for determining chunk type, extracting entity ID, and constructing
    the metadata dictionary.
    """
    text = description.replace("\n", " ")
    if EXAMPLE_PATTERN.search(text):
        img_type = "example"
    elif EXERCISE_PATTERN.search(text):
        img_type = "exercise"
    elif FIGURE_PATTERN.search(text):
        img_type = "captioned_image"
    else:
        img_type = "text"

    decimal_match = re.search(r"((?:\d+|[A-G])\.\d+)", description)
    integer_match = re.search(r"(\d+)", description)

    if img_type == "text":
        entity_id = None
    else:
        entity_id = (
            decimal_match.group(1)
            if decimal_match
            else integer_match.group(1) if integer_match else None
        )

    return {
        "chunk_type": img_type,
        "entity_id": entity_id,
        "page": page_num + 1,
        "image_index": idx + 1,
        "content": description,
        "similarity": round(max_val, 4),
        "bbox": [
            float(max_loc[0]),
            float(max_loc[1]),
            float(max_loc[0] + t_w),
            float(max_loc[1] + t_h),
        ],
    }


def _load_template_gray(figs_doc: Any, idx: int) -> tuple[np.ndarray, int, int]:
    """Load a figure page and convert it to grayscale template plus its dimensions."""
    template_img = pdf_page_to_img(figs_doc, idx)
    template_gray = cv2.cvtColor(template_img, cv2.COLOR_BGR2GRAY)
    t_h, t_w = template_gray.shape[:2]
    return template_gray, t_h, t_w


def _get_cached_page_gray(
    dm_doc: Any, page_ptr: int, page_gray_cache: dict[int, np.ndarray]
) -> np.ndarray:
    """Get a grayscale DM page from cache, rendering it on first access."""
    if page_ptr not in page_gray_cache:
        page_img = pdf_page_to_img(dm_doc, page_ptr)
        page_gray_cache[page_ptr] = cv2.cvtColor(page_img, cv2.COLOR_BGR2GRAY)

        keys_to_remove = [k for k in page_gray_cache if k < page_ptr]
        for k in keys_to_remove:
            del page_gray_cache[k]

    return page_gray_cache[page_ptr]


def _to_fitz_rect(
    max_loc: tuple[int, int], matched_w: int, matched_h: int
) -> tuple[float, float, float, float]:
    """Convert OpenCV pixel bounding box into fitz coordinate space."""
    fitz_scale = get_scale_factor(DPI_RENDER)
    return (
        max_loc[0] * fitz_scale,
        max_loc[1] * fitz_scale,
        (max_loc[0] + matched_w) * fitz_scale,
        (max_loc[1] + matched_h) * fitz_scale,
    )


def _resolve_description_for_match(
    dm_doc: Any,
    page_ptr: int,
    page_obj: Any,
    fitz_rect: tuple[float, float, float, float],
) -> str:
    """Resolve description text for a matched image using override blocks or caption search."""
    prev_page = dm_doc.load_page(page_ptr - 1)
    if page_ptr in FIGURES_DESCRIPTION_BLOCKS:
        page_num, block_idx = FIGURES_DESCRIPTION_BLOCKS[page_ptr]
        page = dm_doc.load_page(page_num)
        blocks = page.get_text("blocks")
        rect = fitz.Rect(blocks[block_idx][:4])
        return str(page.get_text("text", clip=rect).strip().replace("\n", " "))

    return get_advanced_caption(page_obj, prev_page, fitz_rect)


def _scan_pages_for_template(
    dm_doc: Any,
    idx: int,
    template_gray: np.ndarray,
    t_h: int,
    t_w: int,
    page_ptr: int,
    page_gray_cache: dict[int, np.ndarray],
) -> tuple[dict[str, Any] | None, int]:
    """Scan DM pages from page_ptr to find a match and build one metadata entry."""
    while page_ptr < len(dm_doc):
        logger.debug("Scanning page %s", page_ptr + 1)

        if (idx, page_ptr) in SKIP_COMBINATIONS:
            logger.info(
                "Skipping known difficult combination: dm_page=%s fig_page=%s",
                page_ptr + 1,
                idx + 1,
            )
            page_ptr += 1
            continue

        page_gray = _get_cached_page_gray(dm_doc, page_ptr, page_gray_cache)
        page_obj = dm_doc.load_page(page_ptr)

        match_res = _match_template_on_page(page_gray, template_gray)
        if not match_res:
            page_ptr += 1
            continue

        max_val, max_loc, scale = match_res
        matched_w = int(t_w * scale)
        matched_h = int(t_h * scale)
        fitz_rect = _to_fitz_rect(max_loc, matched_w, matched_h)

        description = _resolve_description_for_match(dm_doc, page_ptr, page_obj, fitz_rect)
        entry = _create_entry(
            description,
            page_ptr,
            idx,
            max_val,
            max_loc,
            matched_w,
            matched_h,
        )

        if idx in FIGURES_BBOX_OVERRIDE:
            max_loc, matched_w, matched_h = FIGURES_BBOX_OVERRIDE[idx]

        _mask_matched_region(page_gray, max_loc, matched_w, matched_h)
        return entry, page_ptr

    return None, page_ptr


def process_pdf(
    dm_pdf_path: str | Path,
    figures_pdf_path: str | Path,
    output_json: str = "figures_metadata.json",
) -> None:
    """
    Main processing function that orchestrates the PDF parsing, image matching, caption extraction,
    and result saving.
    """
    all_entries: list[dict[str, Any]] = []

    with fitz.open(dm_pdf_path) as dm_doc, fitz.open(figures_pdf_path) as figs_doc:
        already_found: set[int] = set()
        page_gray_cache: dict[int, np.ndarray] = {}
        page_ptr = 0
        logger.info(f"Processing {len(dm_doc)} pages against {len(figs_doc)} prompt_templates...")

        for idx, _fig in tqdm(enumerate(figs_doc), desc="Searching prompt_templates"):
            logger.info("Processing figure page %s of %s", idx + 1, len(figs_doc))
            if idx in already_found:
                continue

            template_gray, t_h, t_w = _load_template_gray(figs_doc, idx)
            entry, page_ptr = _scan_pages_for_template(
                dm_doc,
                idx,
                template_gray,
                t_h,
                t_w,
                page_ptr,
                page_gray_cache,
            )

            if entry is not None:
                all_entries.append(entry)
                already_found.add(idx)

    _save_to_json(all_entries, output_json)


def _save_to_json(entries: list[dict[str, Any]], filename: str) -> None:
    """Saves the extracted metadata entries to a JSON file with error handling."""
    try:
        output_path = Path(filename)
        with output_path.open("w", encoding="utf-8") as f:
            json.dump(entries, f, indent=2, ensure_ascii=False)
        logger.info(f"Successfully saved {len(entries)} entries to {filename}")
    except OSError as e:
        logger.error(f"Failed to write results to {filename}: {e}")


if __name__ == "__main__":
    process_pdf(MAIN_PDF, FIGURES_PDF)
