import json
import re
from enum import Enum
from pathlib import Path
from typing import Any

import fitz  # type: ignore[import-untyped]
from common.logging import get_logger

from .config import MAIN_PDF, OUTPUT_BLOCKS_JSON


# Module-level constants for geometric analysis
COLUMNS_DIVIDER_X = 300
DISTANCE_BETWEEN_NOTES = 20
DISTANCE_OFFSET_X = 100
GRAY_FILL_THRESHOLD = 0.9

logger = get_logger(__name__)


class BlockType(Enum):
    """Supported types of special document blocks."""

    ALGORITHM = "algorithm"
    EXAMPLE = "example"
    OTHER = "other"


class BlockProcessor:
    """
    Identifies and extracts special content blocks (Algorithms/Examples)
    marked with gray backgrounds and associated side-note captions.
    """

    def __init__(self, pdf_path: str | Path) -> None:
        self.pdf_path = str(pdf_path)
        self.algorithms_pattern = re.compile(r"^Algorithm\s+(?:\d+|[A-G])\.\d+", re.IGNORECASE)
        self.example_pattern = re.compile(r"^Example\s+(?:\d+|[A-G])\.\d+", re.IGNORECASE)

    def _determine_block_type(self, text: str) -> str:
        """Maps detected text to a specific BlockType."""
        clean_text = text.strip()
        if self.algorithms_pattern.match(clean_text):
            return str(BlockType.ALGORITHM.value)
        if self.example_pattern.match(clean_text):
            return str(BlockType.EXAMPLE.value)
        return str(BlockType.OTHER.value)

    def _extract_captions(self, page: Any) -> list[dict[str, Any]]:
        """
        Searches for captions in the side-note column.
        """
        page_dict = page.get_text("dict")
        captions: list[dict[str, Any]] = []
        for block in page_dict.get("blocks", []):
            if "lines" not in block:
                continue

            first_line_text = "".join([span["text"] for span in block["lines"][0]["spans"]])
            b_type = self._determine_block_type(first_line_text)

            if b_type != BlockType.OTHER.value:
                caption_text = ""
                caption_rect: Any | None = None
                prev_y1: float | None = None

                for line in block["lines"]:
                    if line["bbox"][0] > COLUMNS_DIVIDER_X:
                        if prev_y1 and line["bbox"][1] - prev_y1 > DISTANCE_BETWEEN_NOTES:
                            continue

                        line_rect = fitz.Rect(line["bbox"])
                        caption_rect = (
                            line_rect if caption_rect is None else caption_rect | line_rect
                        )
                        caption_text += " ".join([s["text"] for s in line["spans"]]) + " "
                        prev_y1 = float(line["bbox"][3])

                if caption_text and caption_rect:
                    captions.append(
                        {"text": caption_text.strip(), "bbox": caption_rect, "type": b_type}
                    )
        return captions

    def run(self, output_path: str | Path = OUTPUT_BLOCKS_JSON) -> None:
        """
        Main execution loop. Processes PDF pages to link side-note captions
        with gray-filled content blocks.
        """
        all_blocks: list[dict[str, Any]] = []

        with fitz.open(self.pdf_path) as doc:
            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                drawings = page.get_drawings()
                captions = self._extract_captions(page)

                for cap in captions:
                    test_point = fitz.Point(cap["bbox"].x0 - DISTANCE_OFFSET_X, cap["bbox"].y0 + 5)

                    found_match = False
                    for draw in drawings:
                        if (
                            draw["fill"]
                            and draw["fill"][0] > GRAY_FILL_THRESHOLD
                            and draw["rect"].contains(test_point)
                        ):
                            block_rect = draw["rect"]
                            raw_content = page.get_text("text", clip=block_rect).strip()

                            match = re.search(r"(\d+\.\d+)", cap["text"])
                            entity_id = match.group(1) if match else None
                            full_content = f"{cap['text']}\n{raw_content}"

                            all_blocks.append(
                                {
                                    "chunk_type": cap["type"],
                                    "entity_id": entity_id,
                                    "content": full_content,
                                    "caption": cap["text"],
                                    "page": page_num + 1,
                                    "bbox": [
                                        float(block_rect.x0),
                                        float(block_rect.y0),
                                        float(block_rect.x1),
                                        float(block_rect.y1),
                                    ],
                                }
                            )
                            found_match = True
                            break

                    if not found_match:
                        logger.debug("no_drawing_found", caption=cap["text"], page=page_num + 1)

        output_file = Path(output_path)
        with output_file.open("w", encoding="utf-8") as f:
            json.dump(all_blocks, f, indent=2, ensure_ascii=False)

        logger.info("block_extraction_success", total_blocks=len(all_blocks))


if __name__ == "__main__":
    processor = BlockProcessor(MAIN_PDF)
    processor.run()
