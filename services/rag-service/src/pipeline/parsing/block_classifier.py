import json
import re
from enum import Enum
from pathlib import Path
from typing import Any

import fitz  # type: ignore[import-untyped]
from common.logging import get_logger

from .config import MAIN_PDF, OUTPUT_BLOCKS_JSON

# Constants
COLUMNS_DIVIDER_X = 300
DISTANCE_BETWEEN_NOTES = 20
DISTANCE_OFFSET_X = 100
GRAY_FILL_THRESHOLD = 0.9

logger = get_logger(__name__)


class BlockType(Enum):
    ALGORITHM = "algorithm"
    EXAMPLE = "example"
    OTHER = "other"


class BlockProcessor:
    def __init__(self, pdf_path: str | Path) -> None:
        self.pdf_path = str(pdf_path)
        self.algorithms_pattern = re.compile(r"^Algorithm\s+(?:\d+|[A-G])\.\d+", re.IGNORECASE)
        self.example_pattern = re.compile(r"^Example\s+(?:\d+|[A-G])\.\d+", re.IGNORECASE)

    def _determine_block_type(self, text: str) -> str:
        clean_text = text.strip()
        if self.algorithms_pattern.match(clean_text):
            return str(BlockType.ALGORITHM.value)
        if self.example_pattern.match(clean_text):
            return str(BlockType.EXAMPLE.value)
        return str(BlockType.OTHER.value)

    def _extract_captions(self, page: Any) -> list[dict[str, Any]]:
        """Get text blocks from the page and determine if they are captions."""
        page_dict = page.get_text("dict")
        captions: list[dict[str, Any]] = []

        for block in page_dict.get("blocks", []):
            caption = self._process_text_block(block)
            if caption:
                captions.append(caption)
        return captions

    def _process_text_block(self, block: dict[str, Any]) -> dict[str, Any] | None:
        """Check if the block is a caption and extract its text and coordinates."""
        if "lines" not in block or not block["lines"]:
            return None

        first_line_text = "".join([span["text"] for span in block["lines"][0]["spans"]])
        b_type = self._determine_block_type(first_line_text)

        if b_type == BlockType.OTHER.value:
            return None

        return self._assemble_caption_data(block["lines"], b_type)

    def _assemble_caption_data(
        self, lines: list[dict[str, Any]], b_type: str
    ) -> dict[str, Any] | None:
        """Gather text and bounding box for the caption, ensuring it's not a side note."""
        caption_text = ""
        caption_rect: fitz.Rect | None = None
        prev_y1: float | None = None

        for line in lines:
            bbox = line["bbox"]
            if bbox[0] <= COLUMNS_DIVIDER_X:
                continue

            if prev_y1 and bbox[1] - prev_y1 > DISTANCE_BETWEEN_NOTES:
                continue

            line_rect = fitz.Rect(bbox)
            caption_rect = line_rect if caption_rect is None else caption_rect | line_rect
            caption_text += " ".join([s["text"] for s in line["spans"]]) + " "
            prev_y1 = float(bbox[3])

        if not caption_text or not caption_rect:
            return None

        return {"text": caption_text.strip(), "bbox": caption_rect, "type": b_type}

    def _find_matching_drawing(
        self, page: Any, cap: dict[str, Any], drawings: list[dict[str, Any]]
    ) -> fitz.Rect | None:
        """Search for a drawing that contains a point to the left of the caption, indicating it's likely the block's border."""
        test_point = fitz.Point(cap["bbox"].x0 - DISTANCE_OFFSET_X, cap["bbox"].y0 + 5)

        for draw in drawings:
            if not draw.get("fill"):
                continue
            if draw["fill"][0] <= GRAY_FILL_THRESHOLD:
                continue

            if draw["rect"].contains(test_point):
                return draw["rect"]
        return None

    def _create_block_entry(
        self, cap: dict[str, Any], block_rect: fitz.Rect, page_num: int, raw_content: str
    ) -> dict[str, Any]:
        """Form a final dictionary entry for the block."""
        match = re.search(r"(\d+\.\d+)", cap["text"])
        entity_id = match.group(1) if match else None

        return {
            "chunk_type": cap["type"],
            "entity_id": entity_id,
            "content": f"{cap['text']}\n{raw_content}",
            "caption": cap["text"],
            "page": page_num + 1,
            "bbox": [
                float(block_rect.x0),
                float(block_rect.y0),
                float(block_rect.x1),
                float(block_rect.y1),
            ],
        }

    def run(self, output_path: str | Path = OUTPUT_BLOCKS_JSON) -> None:
        """Main processing loop for extracting blocks from PDF."""
        all_blocks: list[dict[str, Any]] = []

        with fitz.open(self.pdf_path) as doc:
            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                drawings = page.get_drawings()
                captions = self._extract_captions(page)

                for cap in captions:
                    block_rect = self._find_matching_drawing(page, cap, drawings)

                    if block_rect:
                        raw_content = page.get_text("text", clip=block_rect).strip()
                        entry = self._create_block_entry(cap, block_rect, page_num, raw_content)
                        all_blocks.append(entry)
                    else:
                        logger.debug("no_drawing_found", caption=cap["text"], page=page_num + 1)

        self._save_results(all_blocks, output_path)

    def _save_results(self, data: list[dict[str, Any]], output_path: str | Path) -> None:
        output_file = Path(output_path)
        with output_file.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info("block_extraction_success", total_blocks=len(data))


if __name__ == "__main__":
    processor = BlockProcessor(MAIN_PDF)
    processor.run()
