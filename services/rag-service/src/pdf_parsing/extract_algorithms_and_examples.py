import json
import re
from enum import Enum
from pathlib import Path

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
                    gray_block["bbox"] = tuple(drawing_rect)
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
                    "block_type": block_type,
                    "page_number": page.number,
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

def get_algorithm_caption_from_jsons(algorithm_number):
    max_x = 0
    max_y = 0
    count = 0
    for json_path in sorted(Path("pdf_jsons").glob("*.json")):
        with json_path.open("r", encoding="utf-8") as fh:
            json_data = json.load(fh)
        for block in json_data:
            for element in block['prunedResult']['parsing_res_list']:
                if algorithm_number in element["block_content"]:
                    # return element["block_content"]
                    count += 1
                    text = element["block_content"]
                    clean = re.sub(r'<[^>]+>', '', text)
                    idx = clean.find(algorithm_number)
                    result = clean[idx:]
                    return result
                # if element["block_bbox"][2] > max_x:
                #     max_x = element["block_bbox"][2]
                # if element["block_bbox"][3] > max_y:
                #     max_y = element["block_bbox"][3]
    print(f"Found {count} captions containing '{algorithm_number}' in JSON files.")
    print("RR: ", max_x, max_y)


def extract_algorithms(pymu_clocks):
    algorithms = []
    for block in pymu_clocks:
        if block["block_type"] != BlockType.ALGORITHM.value:
            continue

        algorithm_number = f"{block["caption"].split(" ")[0]} {block["caption"].split(" ")[1]}"
        # algorithms.append(algorithm_number)
        algorith = {
            "caption": get_algorithm_caption_from_jsons(algorithm_number),
            "text": block["text"],
            "block_type": BlockType.ALGORITHM.value,
        }
        algorithms.append(algorith)
        print(algorith)
    return algorithms

def get_example_by_number(example_number, pymu_clocks):
    for block in pymu_clocks:
        if block["block_type"] != BlockType.EXAMPLE.value:
            continue

        if example_number in block["caption"]:
            return block
    return None



def is_inside(big, small):
    x1b, y1b, x2b, y2b = big[0] / 576, big[1] / 648, big[2] / 576, big[3] / 648
    x1s, y1s, x2s, y2s = small[0] / 1094, small[1] / 1235, small[2] / 1094, small[3] / 1235

    return (
        x1b <= x1s and
        y1b <= y2s and
        x2b + 0.05 >= x2s and
        y2b >= y1s
    )

def get_example_caption(json_page, example_number):
    for element in json_page['prunedResult']['parsing_res_list']:
        if example_number in element["block_content"]:
            # return element["block_content"]
            text = element["block_content"]
            clean = re.sub(r'<[^>]+>', '', text)
            idx = clean.find(example_number)
            result = clean[idx:]
            return result


def extract_example_from_jsons(example):
    example_number = f"{example["caption"].split(" ")[0]} {example["caption"].split(" ")[1]}"
    example_bbox = example["bbox"]
    json_number = example["page_number"] // 100
    json_path = sorted(Path("pdf_jsons").glob("*.json"))[json_number]

    with json_path.open("r", encoding="utf-8") as fh:
        json_data = json.load(fh)

    result_text = ""
    page = json_data[example["page_number"] % 100]
    for element in page['prunedResult']['parsing_res_list']:
        if is_inside(example_bbox, element["block_bbox"]):
            # return element["block_content"]
            text = element["block_content"]
            clean = re.sub(r'<[^>]+>', '', text)
            result_text += f"{clean}\n"

    idx = result_text.find(example_number)
    if idx != -1:
        return {
            "caption": result_text[idx:],
            "text": result_text[:idx],
            "block_type": BlockType.EXAMPLE.value,
        }
    else:
        return {
            "caption": get_example_caption(page, example_number),
            "text": result_text[:idx],
            "block_type": BlockType.EXAMPLE.value,
        }

def extract_examples(example_numbers, pymu_clocks):
    examples = []
    for example_number in example_numbers:
        example = get_example_by_number(example_number, pymu_clocks)
        if example:
            examples.append(extract_example_from_jsons(example))
    return examples
