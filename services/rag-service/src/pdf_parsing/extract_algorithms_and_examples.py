import json
import re
from enum import Enum
from pathlib import Path

import fitz

COLUMNS_DIVIDER_X = 300  # adjust this value based on the actual layout of the PDF
DISTANCE_BETWEEN_NOTES = 20  # distance in pixels to consider a new note or caption
DISTANCE_BETWEEN_POINT_IN_GRAY_BLOCK_AND_CAPTION = 100  # distance in pixels to associate a gray block with a caption
GRAY_FILL_THRESHOLD = 0.9  # fill value to consider block as gray
PADDLE_PAGE_SIZE = (1094, 1235)  # width and height of the page in pixels for normalization in Paddle OCR JSONs
PY_MU_PAGE_SIZE = (576, 648) # width and height of the page in pixels for normalization in muPDF parsed files


class BlockType(Enum):
    """Labels for the gray boxes we want to pull out of the PDF."""

    ALGORITHM = "Algorithm"
    EXAMPLE = "Example"
    OTHER = "Other"


algorithms_pattern = re.compile(r"^Algorithm\s+(?:\d+|[A-G])\.\d+")
example_pattern = re.compile(r"^Example\s+(?:\d+|[A-G])\.\d+")


def _determine_block_type(block):
    """Inspect a PyMuPDF text block dict and classify it as algorithm/example/other."""

    block_text = ""
    for line in block["lines"]:
        for span in line["spans"]:
            block_text += span["text"] + " "

    # Regexes only target the caption prefix at the start of a block.
    if algorithms_pattern.match(block_text):
        return BlockType.ALGORITHM.value

    if example_pattern.match(block_text):
        return BlockType.EXAMPLE.value

    return BlockType.OTHER.value


def _extract_gray_block_caption(block):
    """Collect caption text/rect from the right column of a block until spacing breaks."""

    caption_text = ""

    caption_rect = None

    prev_line_bbox = None
    for line in block["lines"]:
        if line["bbox"][0] > COLUMNS_DIVIDER_X:
            line_bbox = line["bbox"]

            if prev_line_bbox and line_bbox[1] - prev_line_bbox[3] > DISTANCE_BETWEEN_NOTES:
                break
            else:
                prev_line_bbox = line_bbox

            line_rect = fitz.Rect(line["bbox"])

            if caption_rect is None:
                caption_rect = line_rect
            else:
                caption_rect |= line_rect

            for span in line["spans"]:
                caption_text += span["text"] + " "

    return caption_text, caption_rect


def _extract_page_algorithms_and_examples_by_caption(captions, page):
    """Match caption metadata to gray blocks on a page and annotate a copy of the PDF."""

    page_algorithms_and_examples = []
    for caption in captions:
        for drawing in page.get_drawings():
            drawing_rect = drawing["rect"]
            point = fitz.Point(
                caption["caption_rect"][0] - DISTANCE_BETWEEN_POINT_IN_GRAY_BLOCK_AND_CAPTION,
                caption["caption_rect"][1]
            )
            # Point is offset left from the caption to land inside the expected gray box.
            if drawing_rect.contains(point):
                if drawing["fill"] and drawing["fill"][0] > GRAY_FILL_THRESHOLD:

                    gray_block = caption
                    gray_block["text"] = page.get_text("text", clip=drawing_rect)
                    gray_block["bbox"] = tuple(drawing_rect)
                    gray_block["caption_text"] = page.get_text("text", clip=caption["caption_rect"])

                    # Replace caption_rect with caption_bbox for consistency with other callers.
                    gray_block["caption_bbox"] = tuple(caption["caption_rect"])
                    del gray_block["caption_rect"]

                    page_algorithms_and_examples.append(gray_block)
                    break
    return page_algorithms_and_examples


def _extract_page_algorithms_and_examples(page):
    """Build caption metadata for a page and delegate matching block detection."""

    page_gray_block_captions = []
    for block in page.get_text("dict")["blocks"]:
        if "lines" not in block:
            continue

        first_line = block["lines"][0]
        if "spans" not in first_line:
            continue

        block_type = _determine_block_type(block)

        if block_type != BlockType.OTHER.value:
            caption_text, caption_rect = _extract_gray_block_caption(block)

            if caption_text:
                gray_block = {
                    "caption": caption_text,
                    "caption_rect": caption_rect,
                    "block_type": block_type,
                    "page_number": page.number,
                }
                # Keep track of candidate captions so the next stage can find gray fills nearby.
                page_gray_block_captions.append(gray_block)

    return _extract_page_algorithms_and_examples_by_caption(page_gray_block_captions, page)


def extract_algorithms_and_examples(file_path):  # extract algorithms and examples with their captions
    """Return algorithm/example blocks for the given PDF."""

    doc = fitz.open(file_path)
    algorithms_and_examples = []

    for page in doc:
        algorithms_and_examples.extend(_extract_page_algorithms_and_examples(page))
    return algorithms_and_examples


def _strip_html(text: str) -> str:
    """Remove simple HTML tags embedded in OCR JSON content."""
    return re.sub(r"<[^>]+>", "", text)


def _caption_key_from_caption(caption: str) -> str:
    """Normalize a caption into its stable key (e.g., 'Example 2.3.')."""
    parts = caption.split()
    if len(parts) < 2:
        return caption
    return f"{parts[0]} {parts[1]}"


def get_algorithm_caption_from_jsons(algorithm_number):
    """Find the full algorithm caption by scanning OCR JSON pages."""
    for json_path in sorted(Path("pdf_jsons").glob("*.json")):
        with json_path.open("r", encoding="utf-8") as fh:
            json_data = json.load(fh)
        for block in json_data:
            for element in block["prunedResult"]["parsing_res_list"]:
                if algorithm_number in element["block_content"]:
                    text = element["block_content"]
                    clean = _strip_html(text)
                    idx = clean.find(algorithm_number)
                    return clean[idx:]
    return None


def extract_algorithms(pymu_blocks):
    """Extract algorithm blocks and hydrate captions via OCR JSON metadata."""
    algorithms = []
    for block in pymu_blocks:
        if block["block_type"] != BlockType.ALGORITHM.value:
            continue

        algorithm_number = _caption_key_from_caption(block["caption"])
        algorithm = {
            "caption": get_algorithm_caption_from_jsons(algorithm_number),
            "text": block["text"],
            "block_type": BlockType.ALGORITHM.value,
        }
        algorithms.append(algorithm)
    return algorithms


def get_example_by_number(example_number, pymu_blocks):
    """Return the first matching example block by caption number."""
    for block in pymu_blocks:
        if block["block_type"] != BlockType.EXAMPLE.value:
            continue

        if example_number in block["caption"]:
            return block
    return None


def _normalize_bbox(bbox, page_size):
    """Normalize a bbox tuple to 0..1 space using the provided page size."""
    width, height = page_size
    x1, y1, x2, y2 = bbox
    return (x1 / width, y1 / height, x2 / width, y2 / height)


def is_inside_bbox(big, small):
    """Check whether a smaller bbox is inside a larger one using normalized coordinates."""
    x1b, y1b, x2b, y2b = _normalize_bbox(big, PY_MU_PAGE_SIZE)
    x1s, y1s, x2s, y2s = _normalize_bbox(small, PADDLE_PAGE_SIZE)

    error = 0.05
    return (
        x1b <= x1s and
        y1b <= y2s and
        x2b + error >= x2s and
        y2b >= y1s
    )


def get_example_caption(json_page, example_number):
    """Extract an example caption from a single OCR JSON page."""
    for element in json_page["prunedResult"]["parsing_res_list"]:
        if example_number in element["block_content"]:
            text = element["block_content"]
            clean = _strip_html(text)
            idx = clean.find(example_number)
            return clean[idx:]


def extract_example_from_jsons(example):
    """Rebuild a full example block by intersecting OCR JSON text with a PDF bbox."""
    example_number = _caption_key_from_caption(example["caption"])
    example_bbox = example["bbox"]
    json_number = example["page_number"] // 100
    json_path = sorted(Path("pdf_jsons").glob("*.json"))[json_number]

    with json_path.open("r", encoding="utf-8") as fh:
        json_data = json.load(fh)

    result_text = ""
    page = json_data[example["page_number"] % 100]
    for element in page["prunedResult"]["parsing_res_list"]:
        if is_inside_bbox(example_bbox, element["block_bbox"]):
            text = element["block_content"]
            clean = _strip_html(text)
            result_text += f"{clean}\n"

    idx = result_text.find(example_number)
    if idx != -1:
        return {
            "caption": result_text[idx:],
            "text": result_text[:idx],
            "block_type": BlockType.EXAMPLE.value,
        }
    else:
        # Fall back to caption-only lookup if the split point was not found.
        return {
            "caption": get_example_caption(page, example_number),
            "text": result_text[:idx],
            "block_type": BlockType.EXAMPLE.value,
        }


def extract_examples(example_numbers, pymu_blocks):
    """Extract a list of examples by number using PDF and OCR JSON data."""
    examples = []
    for example_number in example_numbers:
        example = get_example_by_number(example_number, pymu_blocks)
        if example:
            examples.append(extract_example_from_jsons(example))
    return examples
