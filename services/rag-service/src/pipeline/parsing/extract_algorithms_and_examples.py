import json
import re
from collections.abc import Iterable, Sequence
from enum import Enum
from pathlib import Path
from typing import Any

import fitz  # type: ignore[import-not-found]
from tqdm import tqdm  # type: ignore[import-untyped]

COLUMNS_DIVIDER_X = 300  # adjust this value based on the actual layout of the PDF
DISTANCE_BETWEEN_NOTES = 20  # distance in pixels to consider a new note or caption
DISTANCE_BETWEEN_POINT_IN_GRAY_BLOCK_AND_CAPTION = (
    100  # distance in pixels to associate a gray block with a caption
)
GRAY_FILL_THRESHOLD = 0.9  # fill value to consider block as gray
PADDLE_PAGE_SIZE = (
    1094,
    1235,
)  # width and height of the page in pixels for normalization in Paddle OCR JSONs
PY_MU_PAGE_SIZE = (
    576,
    648,
)  # width and height of the page in pixels for normalization in muPDF parsed files


class BlockType(Enum):
    """Labels for the gray boxes we want to pull out of the PDF."""

    ALGORITHM = "Algorithm"
    EXAMPLE = "Example"
    OTHER = "Other"


algorithms_pattern = re.compile(r"^Algorithm\s+(?:\d+|[A-G])\.\d+", re.IGNORECASE)
example_pattern = re.compile(r"^Example\s+(?:\d+|[A-G])\.\d+", re.IGNORECASE)

BlockData = dict[str, Any]
PyMuPDFBlock = dict[str, Any]
PyMuPDFPage = Any
JsonPage = dict[str, Any]


class BlockProcessor:
    """Extract algorithm/example gray blocks and serialize them to JSON."""

    def __init__(self, pdf_path: str, pdf_jsons_dir: str | Path = "pdf_jsons"):
        """Open the PDF and set the directory used for OCR JSON lookups."""
        self._pdf_path = pdf_path
        self._doc: fitz.Document | None = None
        self.algorithms_pattern = algorithms_pattern
        self.example_pattern = example_pattern
        self.pdf_jsons_dir = Path(pdf_jsons_dir)

    def __enter__(self) -> "BlockProcessor":
        self._get_doc()
        return self

    def __exit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: Any | None
    ) -> None:
        self.close()

    def _get_doc(self) -> fitz.Document:
        if self._doc is None:
            self._doc = fitz.open(self._pdf_path)
        return self._doc

    def close(self) -> None:
        if self._doc is not None:
            self._doc.close()
            self._doc = None

    def _determine_block_type_from_text(self, text: str) -> str:
        """Classify a caption string as algorithm/example/other."""
        clean_text = text.strip()
        if self.algorithms_pattern.match(clean_text):
            return BlockType.ALGORITHM.value
        if self.example_pattern.match(clean_text):
            return BlockType.EXAMPLE.value
        return BlockType.OTHER.value

    def _determine_block_type_from_block(self, block: PyMuPDFBlock) -> str:
        """Inspect a PyMuPDF text block dict and classify it as algorithm/example/other."""
        block_text = ""
        for line in block["lines"]:
            for span in line["spans"]:
                block_text += span["text"] + " "

        if self.algorithms_pattern.match(block_text):
            return BlockType.ALGORITHM.value

        if self.example_pattern.match(block_text):
            return BlockType.EXAMPLE.value

        return BlockType.OTHER.value

    def _extract_gray_block_caption(self, block: PyMuPDFBlock) -> tuple[str, Any | None]:
        """Collect caption text/rect from the right column of a block until spacing breaks."""
        caption_text = ""
        caption_rect = None

        prev_line_bbox = None
        for line in block["lines"]:
            if line["bbox"][0] > COLUMNS_DIVIDER_X:
                line_bbox = line["bbox"]

                if prev_line_bbox and line_bbox[1] - prev_line_bbox[3] > DISTANCE_BETWEEN_NOTES:
                    break

                prev_line_bbox = line_bbox
                line_rect = fitz.Rect(line_bbox)
                caption_rect = line_rect if caption_rect is None else (caption_rect | line_rect)

                for span in line["spans"]:
                    caption_text += span["text"] + " "

        return caption_text, caption_rect

    def _extract_captions(self, page: PyMuPDFPage) -> list[BlockData]:
        """Collect caption text and bounding boxes from the right column."""
        page_dict = page.get_text("dict")
        captions = []
        for block in page_dict.get("blocks", []):
            if "lines" not in block:
                continue

            first_line = block["lines"][0]
            if "spans" not in first_line:
                continue

            first_line_text = "".join(span["text"] for span in first_line["spans"])
            block_type = self._determine_block_type_from_text(first_line_text)

            if block_type == BlockType.OTHER.value:
                continue

            caption_text = ""
            caption_rect = None
            prev_line_bbox = None
            for line in block["lines"]:
                if line["bbox"][0] > COLUMNS_DIVIDER_X:
                    line_bbox = line["bbox"]

                    if prev_line_bbox and line_bbox[1] - prev_line_bbox[3] > DISTANCE_BETWEEN_NOTES:
                        break

                    prev_line_bbox = line_bbox
                    line_rect = fitz.Rect(line_bbox)
                    caption_rect = line_rect if caption_rect is None else (caption_rect | line_rect)
                    caption_text += " ".join(span["text"] for span in line["spans"]) + " "

            if caption_text and caption_rect:
                captions.append(
                    {
                        "text": caption_text.strip(),
                        "bbox": caption_rect,
                        "type": block_type,
                    }
                )
        return captions

    def _extract_page_algorithms_and_examples_by_caption(
        self, captions: list[BlockData], page: PyMuPDFPage
    ) -> list[BlockData]:
        """Match caption metadata to gray blocks on a page and annotate a copy of the PDF."""
        page_algorithms_and_examples: list[BlockData] = []
        for caption in captions:
            for drawing in page.get_drawings():
                drawing_rect = drawing["rect"]
                point = fitz.Point(
                    caption["caption_rect"][0] - DISTANCE_BETWEEN_POINT_IN_GRAY_BLOCK_AND_CAPTION,
                    caption["caption_rect"][1],
                )
                if drawing_rect.contains(point) and (
                    drawing["fill"] and drawing["fill"][0] > GRAY_FILL_THRESHOLD
                ):
                    gray_block = caption
                    gray_block["text"] = page.get_text("text", clip=drawing_rect)
                    gray_block["bbox"] = tuple(drawing_rect)
                    gray_block["caption_text"] = page.get_text("text", clip=caption["caption_rect"])

                    gray_block["caption_bbox"] = tuple(caption["caption_rect"])
                    del gray_block["caption_rect"]

                    page_algorithms_and_examples.append(gray_block)
                    break
        return page_algorithms_and_examples

    def _extract_page_algorithms_and_examples(self, page: PyMuPDFPage) -> list[BlockData]:
        """Build caption metadata for a page and delegate matching block detection."""
        page_gray_block_captions = []
        for block in page.get_text("dict")["blocks"]:
            if "lines" not in block:
                continue

            first_line = block["lines"][0]
            if "spans" not in first_line:
                continue

            block_type = self._determine_block_type_from_block(block)

            if block_type != BlockType.OTHER.value:
                caption_text, caption_rect = self._extract_gray_block_caption(block)

                if caption_text:
                    gray_block = {
                        "caption": caption_text,
                        "caption_rect": caption_rect,
                        "block_type": block_type,
                        "page_number": page.number,
                    }
                    page_gray_block_captions.append(gray_block)

        return self._extract_page_algorithms_and_examples_by_caption(page_gray_block_captions, page)

    def extract_algorithms_and_examples(self) -> list[BlockData]:
        """Return algorithm/example blocks for the opened PDF."""
        algorithms_and_examples: list[BlockData] = []
        for page in self._get_doc():
            algorithms_and_examples.extend(self._extract_page_algorithms_and_examples(page))
        return algorithms_and_examples

    def _strip_html(self, text: str) -> str:
        """Remove simple HTML tags embedded in OCR JSON content."""
        return re.sub(r"<[^>]+>", "", text)

    def _caption_key_from_caption(self, caption: str) -> str:
        """Normalize a caption into its stable key (e.g., 'Example 2.3.')."""
        parts = caption.split()
        if len(parts) < 2:
            return caption
        return f"{parts[0]} {parts[1]}"

    def get_algorithm_caption_from_jsons(self, algorithm_number: str) -> str | None:
        """Find the full algorithm caption by scanning OCR JSON pages."""
        for json_path in sorted(self.pdf_jsons_dir.glob("*.json")):
            with json_path.open("r", encoding="utf-8") as fh:
                json_data = json.load(fh)
            for block in json_data:
                for element in block["prunedResult"]["parsing_res_list"]:
                    if algorithm_number in element["block_content"]:
                        text = element["block_content"]
                        clean = self._strip_html(text)
                        idx = clean.find(algorithm_number)
                        return clean[idx:]
        return None

    def extract_algorithms(self, pymu_blocks: list[BlockData]) -> list[BlockData]:
        """Extract algorithm blocks and hydrate captions via OCR JSON metadata."""
        algorithms: list[BlockData] = []
        for block in pymu_blocks:
            if block["block_type"] != BlockType.ALGORITHM.value:
                continue

            algorithm_number = self._caption_key_from_caption(block["caption"])
            caption = self.get_algorithm_caption_from_jsons(algorithm_number)
            if caption is None:
                # Fallback to the original caption from the block or, if unavailable,
                # to the normalized algorithm number key.
                caption = block.get("caption") or algorithm_number
            algorithm = {
                "caption": caption,
                "text": block["text"],
                "block_type": BlockType.ALGORITHM.value,
            }
            algorithms.append(algorithm)
        return algorithms

    def get_example_by_number(
        self, example_number: str, pymu_blocks: list[BlockData]
    ) -> BlockData | None:
        """Return the first matching example block by caption number."""
        for block in pymu_blocks:
            if block["block_type"] != BlockType.EXAMPLE.value:
                continue

            if example_number in block["caption"]:
                return block
        return None

    def _normalize_bbox(
        self, bbox: Sequence[float], page_size: Sequence[float]
    ) -> tuple[float, float, float, float]:
        """Normalize a bbox tuple to 0..1 space using the provided page size."""
        width, height = page_size
        x1, y1, x2, y2 = bbox
        return (x1 / width, y1 / height, x2 / width, y2 / height)

    def is_inside_bbox(self, big: Sequence[float], small: Sequence[float]) -> bool:
        """Check whether a smaller bbox is inside a larger one using normalized coordinates."""
        x1b, y1b, x2b, y2b = self._normalize_bbox(big, PY_MU_PAGE_SIZE)
        x1s, y1s, x2s, y2s = self._normalize_bbox(small, PADDLE_PAGE_SIZE)

        error = 0.05
        return x1b <= x1s and y1b <= y2s and x2b + error >= x2s and y2b >= y1s

    def get_example_caption(self, json_page: JsonPage, example_number: str) -> str | None:
        """Extract an example caption from a single OCR JSON page."""
        for element in json_page["prunedResult"]["parsing_res_list"]:
            if example_number in element["block_content"]:
                text = element["block_content"]
                clean = self._strip_html(text)
                idx = clean.find(example_number)
                return clean[idx:]
        return None

    def extract_example_from_jsons(self, example: BlockData) -> BlockData:
        """Rebuild a full example block by intersecting OCR JSON text with a PDF bbox."""
        example_number = self._caption_key_from_caption(example["caption"])
        example_bbox = example["bbox"]
        json_number = example["page_number"] // 100
        json_path = sorted(self.pdf_jsons_dir.glob("*.json"))[json_number]

        with json_path.open("r", encoding="utf-8") as fh:
            json_data = json.load(fh)

        result_text = ""
        page = json_data[example["page_number"] % 100]
        for element in page["prunedResult"]["parsing_res_list"]:
            if self.is_inside_bbox(example_bbox, element["block_bbox"]):
                text = element["block_content"]
                clean = self._strip_html(text)
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
                "caption": self.get_example_caption(page, example_number),
                "text": result_text[:idx],
                "block_type": BlockType.EXAMPLE.value,
            }

    def extract_examples(
        self, example_numbers: Iterable[str], pymu_blocks: list[BlockData]
    ) -> list[BlockData]:
        """Extract a list of examples by number using PDF and OCR JSON data."""
        examples: list[BlockData] = []
        for example_number in example_numbers:
            example = self.get_example_by_number(example_number, pymu_blocks)
            if example:
                examples.append(self.extract_example_from_jsons(example))
        return examples

    def run(self, output_path: str | Path = "blocks_metadata.json") -> None:
        """Extract blocks and dump their metadata to JSON."""
        all_blocks = []
        doc = self._get_doc()
        try:
            for page_num in tqdm(range(len(doc)), desc="Extracting gray blocks"):
                page = doc.load_page(page_num)
                drawings = page.get_drawings()
                captions = self._extract_captions(page)

                for caption in captions:
                    test_point = fitz.Point(
                        caption["bbox"].x0 - DISTANCE_BETWEEN_POINT_IN_GRAY_BLOCK_AND_CAPTION,
                        caption["bbox"].y0 + 5,
                    )

                    for drawing in drawings:
                        if (
                            drawing["fill"]
                            and drawing["fill"][0] > GRAY_FILL_THRESHOLD
                            and drawing["rect"].contains(test_point)
                        ):
                            block_rect = drawing["rect"]
                            raw_content = page.get_text("text", clip=block_rect).strip()

                            match = re.search(r"(\d+\.\d+)", caption["text"])
                            entity_id = match.group(1) if match else None

                            all_blocks.append(
                                {
                                    "chunk_type": caption["type"],
                                    "entity_id": entity_id,
                                    "content": raw_content,
                                    "caption": caption["text"],
                                    "page": page_num + 1,
                                    "bbox": [
                                        block_rect.x0,
                                        block_rect.y0,
                                        block_rect.x1,
                                        block_rect.y1,
                                    ],
                                }
                            )
                            break
        finally:
            self.close()

        output_path = Path(output_path)
        with output_path.open("w", encoding="utf-8") as fh:
            json.dump(all_blocks, fh, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    with BlockProcessor("dm.pdf") as processor:
        processor.run()
