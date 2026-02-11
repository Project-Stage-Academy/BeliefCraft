import re
from enum import Enum

import fitz

COLUMNS_DIVIDER_X = 300  # adjust this value based on the actual layout of the PDF
DISTANCE_BETWEEN_NOTES = 20  # distance in pixels to consider a new note or caption
DiSTANCE_BETWEEN_POINT_IN_GRAY_BLOCK_AND_CAPTION = 100  # distance in pixels to associate a gray block with a caption
GRAY_FILL_THRESHOLD = 0.9  # fill value to consider block as gray

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
                caption["caption_rect"][0] - DiSTANCE_BETWEEN_POINT_IN_GRAY_BLOCK_AND_CAPTION,
                caption["caption_rect"][1]
            )
            # Point is offset left from the caption to land inside the expected gray box.
            if drawing_rect.contains(point):
                if drawing["fill"] and drawing["fill"][0] > GRAY_FILL_THRESHOLD:

                    gray_block = caption
                    gray_block["text"] = page.get_text("text", clip=drawing_rect)
                    gray_block["caption_text"] = page.get_text("text", clip=caption["caption_rect"])

                    # replace caption_rect with caption_bbox for consistency
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
                    "block_type": block_type
                }
                # Keep track of candidate captions so the next stage can find gray fills nearby.
                page_gray_block_captions.append(gray_block)

    return _extract_page_algorithms_and_examples_by_caption(page_gray_block_captions, page)


def extract_algorithms_and_examples(file_path):  # extract algorithms and examples with their captions
    """Return algorithm/example blocks for the given PDF, also persisting an annotated copy."""

    doc = fitz.open(file_path)
    algorithms_and_examples = []

    for page in doc:
        algorithms_and_examples.extend(_extract_page_algorithms_and_examples(page))
    return algorithms_and_examples
