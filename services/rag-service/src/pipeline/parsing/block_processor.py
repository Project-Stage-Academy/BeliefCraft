import json
import re
from collections.abc import Iterable, Iterator, Sequence
from contextlib import contextmanager
from enum import Enum
from pathlib import Path
from typing import Any, cast

import fitz  # type: ignore[import-untyped]
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


class CaptionFinder:
    """Classify blocks and extract captions and gray-block metadata."""

    def __init__(
        self,
        algorithms_re: re.Pattern[str],
        examples_re: re.Pattern[str],
        columns_divider_x: int = COLUMNS_DIVIDER_X,
        distance_between_notes: int = DISTANCE_BETWEEN_NOTES,
    ) -> None:
        self._algorithms_re = algorithms_re
        self._examples_re = examples_re
        self._columns_divider_x = columns_divider_x
        self._distance_between_notes = distance_between_notes

    def classify_text(self, text: str) -> str:
        clean_text = text.strip()
        if self._algorithms_re.match(clean_text):
            return BlockType.ALGORITHM.value
        if self._examples_re.match(clean_text):
            return BlockType.EXAMPLE.value
        return BlockType.OTHER.value

    def classify_block(self, block: PyMuPDFBlock) -> str:
        block_text = ""
        for line in block["lines"]:
            for span in line["spans"]:
                block_text += span["text"] + " "

        if self._algorithms_re.match(block_text):
            return BlockType.ALGORITHM.value

        if self._examples_re.match(block_text):
            return BlockType.EXAMPLE.value

        return BlockType.OTHER.value

    def _extract_gray_block_caption(self, block: PyMuPDFBlock) -> tuple[str, Any | None]:
        caption_text = ""
        caption_rect = None

        prev_line_bbox = None
        for line in block["lines"]:
            if line["bbox"][0] > self._columns_divider_x:
                line_bbox = line["bbox"]

                if (
                    prev_line_bbox
                    and line_bbox[1] - prev_line_bbox[3] > self._distance_between_notes
                ):
                    break

                prev_line_bbox = line_bbox
                line_rect = fitz.Rect(line_bbox)
                caption_rect = line_rect if caption_rect is None else (caption_rect | line_rect)

                for span in line["spans"]:
                    if span["text"].strip():
                        caption_text += span["text"] + " "

        return caption_text, caption_rect

    def extract_captions(self, page: PyMuPDFPage) -> list[BlockData]:
        page_dict = page.get_text("dict")
        captions = []
        for block in page_dict.get("blocks", []):
            if "lines" not in block:
                continue

            first_line = block["lines"][0]
            if "spans" not in first_line:
                continue

            first_line_text = "".join(span["text"] for span in first_line["spans"])

            if first_line_text in ("Example", "Algorithm"):
                second_line = block["lines"][1]
                if "spans" not in second_line:
                    continue

                first_line_text += " " + "".join(span["text"] for span in second_line["spans"])

            block_type = self.classify_text(first_line_text)

            if block_type == BlockType.OTHER.value:
                continue

            caption_text = ""
            caption_rect = None
            prev_line_bbox = None
            for line in block["lines"]:
                if line["bbox"][0] > self._columns_divider_x:
                    line_bbox = line["bbox"]

                    if (
                        prev_line_bbox
                        and line_bbox[1] - prev_line_bbox[3] > self._distance_between_notes
                    ):
                        break

                    prev_line_bbox = line_bbox
                    line_rect = fitz.Rect(line_bbox)
                    caption_rect = line_rect if caption_rect is None else (caption_rect | line_rect)
                    caption_text += (
                        " ".join(span["text"] for span in line["spans"] if span["text"].strip())
                        + " "
                    )

            if caption_text and caption_rect:
                captions.append(
                    {
                        "text": caption_text.strip(),
                        "bbox": caption_rect,
                        "type": block_type,
                    }
                )
        return captions

    def extract_page_gray_block_captions(self, page: PyMuPDFPage) -> list[BlockData]:
        page_gray_block_captions = []
        for block in page.get_text("dict")["blocks"]:
            if "lines" not in block:
                continue

            first_line = block["lines"][0]
            if "spans" not in first_line:
                continue

            block_type = self.classify_block(block)

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

        return page_gray_block_captions


class GrayBlockMatcher:
    """Match captions to gray blocks within a page."""

    def __init__(
        self,
        distance_between_block_and_caption: int = DISTANCE_BETWEEN_POINT_IN_GRAY_BLOCK_AND_CAPTION,
        gray_fill_threshold: float = GRAY_FILL_THRESHOLD,
    ) -> None:
        self._distance_between_block_and_caption = distance_between_block_and_caption
        self._gray_fill_threshold = gray_fill_threshold

    def match(self, captions: list[BlockData], page: PyMuPDFPage) -> list[BlockData]:
        page_algorithms_and_examples: list[BlockData] = []
        for caption in captions:
            for drawing in page.get_drawings():
                drawing_rect = drawing["rect"]
                point = fitz.Point(
                    caption["caption_rect"][0] - self._distance_between_block_and_caption,
                    caption["caption_rect"][1],
                )
                if drawing_rect.contains(point) and (
                    drawing["fill"] and drawing["fill"][0] > self._gray_fill_threshold
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


class OcrCaptionRepository:
    """Access OCR JSON pages and provide caption utilities."""

    def __init__(self, paddle_ocr_dir: str | Path) -> None:
        self._paddle_ocr_dir = Path(paddle_ocr_dir)

    def iter_json_pages(self) -> Iterable[Path]:
        pages = sorted(self._paddle_ocr_dir.glob("*.json"))
        if not pages:
            raise FileNotFoundError(f"No OCR JSON files found in `{self._paddle_ocr_dir}`")
        return pages

    @staticmethod
    def strip_html(text: str) -> str:
        return re.sub(r"<[^>]+>", "", text)

    def load_json(self, json_path: Path) -> list[dict[str, Any]]:
        with json_path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        return cast(list[dict[str, Any]], data)

    @staticmethod
    def caption_key_from_caption(caption: str) -> str:
        parts = caption.split()
        if len(parts) < 2:
            return caption
        return f"{parts[0]} {parts[1]}"

    def get_algorithm_caption(self, algorithm_number: str) -> str | None:
        for json_path in self.iter_json_pages():
            json_data = self.load_json(json_path)
            for block in json_data:
                for element in block["prunedResult"]["parsing_res_list"]:
                    if algorithm_number in element["block_content"]:
                        text = element["block_content"]
                        clean = self.strip_html(text)
                        idx = clean.find(algorithm_number)
                        return clean[idx:]
        return None

    def get_example_caption(self, json_page: JsonPage, example_number: str) -> str | None:
        for element in json_page["prunedResult"]["parsing_res_list"]:
            if example_number in element["block_content"]:
                text = element["block_content"]
                clean = self.strip_html(text)
                idx = clean.find(example_number)
                return clean[idx:]
        return None


class BlockHydrator:
    """Hydrate algorithm and example blocks using OCR JSON metadata."""

    def __init__(
        self,
        ocr_repo: OcrCaptionRepository,
        paddle_page_size: Sequence[float] = PADDLE_PAGE_SIZE,
        pymu_page_size: Sequence[float] = PY_MU_PAGE_SIZE,
        error: float = 0.05,
    ) -> None:
        self._ocr_repo = ocr_repo
        self._paddle_page_size = paddle_page_size
        self._pymu_page_size = pymu_page_size
        self._error = error

    def _normalize_bbox(
        self, bbox: Sequence[float], page_size: Sequence[float]
    ) -> tuple[float, float, float, float]:
        width, height = page_size
        x1, y1, x2, y2 = bbox
        return (x1 / width, y1 / height, x2 / width, y2 / height)

    def _is_inside_bbox(self, big: Sequence[float], small: Sequence[float]) -> bool:
        x1b, y1b, x2b, y2b = self._normalize_bbox(big, self._pymu_page_size)
        x1s, y1s, x2s, y2s = self._normalize_bbox(small, self._paddle_page_size)

        return x1b <= x1s and y1b <= y2s and x2b + self._error >= x2s and y2b >= y1s

    def _get_example_by_number(
        self, example_number: str, pymu_blocks: list[BlockData]
    ) -> BlockData | None:
        for block in pymu_blocks:
            if block["block_type"] != BlockType.EXAMPLE.value:
                continue

            if example_number in block["caption"]:
                return block
        return None

    def _extract_example_from_jsons(self, example: BlockData) -> BlockData:
        example_number = self._ocr_repo.caption_key_from_caption(example["caption"])
        example_bbox = example["bbox"]
        json_number = example["page_number"] // 100
        json_path = list(self._ocr_repo.iter_json_pages())[json_number]

        json_data = self._ocr_repo.load_json(json_path)

        result_text = ""
        page = json_data[example["page_number"] % 100]
        for element in page["prunedResult"]["parsing_res_list"]:
            if self._is_inside_bbox(example_bbox, element["block_bbox"]):
                text = element["block_content"]
                clean = self._ocr_repo.strip_html(text)
                result_text += f"{clean}\n"

        idx = result_text.find(example_number)
        if idx != -1:
            return {
                "caption": result_text[idx:],
                "text": result_text[:idx],
                "block_type": BlockType.EXAMPLE.value,
            }

        return {
            "caption": self._ocr_repo.get_example_caption(page, example_number),
            "text": result_text[:idx],
            "block_type": BlockType.EXAMPLE.value,
        }

    def extract_examples(
        self, example_numbers: Iterable[str], pymu_blocks: list[BlockData]
    ) -> list[BlockData]:
        examples: list[BlockData] = []
        for example_number in example_numbers:
            example = self._get_example_by_number(example_number, pymu_blocks)
            if example:
                examples.append(self._extract_example_from_jsons(example))
        return examples

    def extract_algorithms(self, pymu_blocks: list[BlockData]) -> list[BlockData]:
        algorithms: list[BlockData] = []
        for block in pymu_blocks:
            if block["block_type"] != BlockType.ALGORITHM.value:
                continue

            algorithm_number = self._ocr_repo.caption_key_from_caption(block["caption"])
            caption = self._ocr_repo.get_algorithm_caption(algorithm_number)
            if caption is None:
                caption = block.get("caption") or algorithm_number
            algorithm = {
                "caption": caption,
                "text": block["text"],
                "block_type": BlockType.ALGORITHM.value,
            }
            algorithms.append(algorithm)
        return algorithms


class BlockProcessor:
    """Extract algorithm/example gray blocks and serialize them to JSON."""

    def __init__(
        self,
        pdf_path: str,
        *,
        caption_finder: CaptionFinder,
        gray_block_matcher: GrayBlockMatcher,
        block_hydrator: BlockHydrator,
    ):
        """Open the PDF and set the directory used for OCR JSON lookups."""
        self._pdf_path = pdf_path
        self._doc: fitz.Document | None = None
        self._caption_finder = caption_finder
        self._gray_block_matcher = gray_block_matcher
        self._block_hydrator = block_hydrator

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

    def _extract_page_algorithms_and_examples(self, page: PyMuPDFPage) -> list[BlockData]:
        page_gray_block_captions = self._caption_finder.extract_page_gray_block_captions(page)
        return self._gray_block_matcher.match(page_gray_block_captions, page)

    def extract_algorithms_and_examples(self) -> list[BlockData]:
        algorithms_and_examples: list[BlockData] = []
        for page in self._get_doc():
            algorithms_and_examples.extend(self._extract_page_algorithms_and_examples(page))
        return algorithms_and_examples

    def extract_algorithms(self, pymu_blocks: list[BlockData]) -> list[BlockData]:
        return self._block_hydrator.extract_algorithms(pymu_blocks)

    def extract_examples(
        self, example_numbers: Iterable[str], pymu_blocks: list[BlockData]
    ) -> list[BlockData]:
        return self._block_hydrator.extract_examples(example_numbers, pymu_blocks)

    def _find_gray_block_rect(
        self, drawings: list[dict[str, Any]], caption_bbox: fitz.Rect
    ) -> fitz.Rect | None:
        test_point = fitz.Point(
            caption_bbox.x0 - DISTANCE_BETWEEN_POINT_IN_GRAY_BLOCK_AND_CAPTION,
            caption_bbox.y0 + 5,
        )
        for drawing in drawings:
            if (
                drawing["fill"]
                and drawing["fill"][0] > GRAY_FILL_THRESHOLD
                and drawing["rect"].contains(test_point)
            ):
                return drawing["rect"]
        return None

    @staticmethod
    def _extract_entity_id(caption_text: str) -> str | None:
        match = re.search(r"(\d+\.\d+)", caption_text)
        return match.group(1) if match else None

    def run(self, output_path: str | Path = "blocks_metadata.json") -> None:
        """Extract blocks and dump their metadata to JSON."""
        all_blocks = []
        doc = self._get_doc()
        try:
            for page_num in tqdm(range(len(doc)), desc="Extracting gray blocks"):
                page = doc.load_page(page_num)
                drawings = page.get_drawings()
                captions = self._caption_finder.extract_captions(page)

                for caption in captions:
                    block_rect = self._find_gray_block_rect(drawings, caption["bbox"])
                    if block_rect is None:
                        continue

                    raw_content = page.get_text("text", clip=block_rect).strip()
                    entity_id = self._extract_entity_id(caption["text"])

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
        finally:
            self.close()

        output_path = Path(output_path)
        with output_path.open("w", encoding="utf-8") as fh:
            json.dump(all_blocks, fh, indent=2, ensure_ascii=False)


@contextmanager
def open_block_processor(
    pdf_path: str,
    paddle_ocr_dir: str | Path,
) -> Iterator["BlockProcessor"]:
    """Yield a BlockProcessor with default collaborators wired."""
    caption_finder = CaptionFinder(algorithms_pattern, example_pattern)
    gray_block_matcher = GrayBlockMatcher()
    ocr_repo = OcrCaptionRepository(paddle_ocr_dir)
    block_hydrator = BlockHydrator(ocr_repo)

    with BlockProcessor(
        pdf_path,
        caption_finder=caption_finder,
        gray_block_matcher=gray_block_matcher,
        block_hydrator=block_hydrator,
    ) as processor:
        yield processor


if __name__ == "__main__":
    processor: BlockProcessor
    with open_block_processor("dm.pdf", "ocr_json") as processor:
        processor.run()
