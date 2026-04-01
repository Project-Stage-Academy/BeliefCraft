import contextlib
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup
from common.logging import configure_logging, get_logger
from dotenv import load_dotenv
from pipeline.parsing.math_table_engine import clean_html_attributes

try:
    from .metadata_extractor import MetadataExtractor
except ImportError:
    from metadata_extractor import MetadataExtractor  # type: ignore


FIGURES_BUCKET_URL = os.getenv("FIGURES_BUCKET_URL", "").rstrip("/") + "/"

configure_logging("rag-service", log_level="INFO")
logger = get_logger(__name__)

logger.info("service_started", message="RAG Service is up and running")

START_PAGE = 23
LAST_PAGE = 648
BBOX_PADDING = 5
MAX_CHUNK_CHAR_LENGTH = 1000
PADDLE_BLOCKS_TO_SKIP = ["footer", "number", "header", "image", "footnote", "doc_title", "chart"]
# current algorithms fails for these pages
PAGES_NOT_TO_FIX_PADDLE = {55, 58, 128, 316, 437, 500, 568}

PART_SEQUENCE = ["I", "II", "III", "IV", "V", "Appendices"]
IMAGE_SCALE = 0.36  # 72 points per inch / 200 dpi
FITZ_WIDTH = 576
FITZ_HEIGHT = 648
PADDLE_WIDTH = 1152
PADDLE_HEIGHT = 1296

NOTE_NUMBER_PATTERN = r"\$+\s\^\{(\d+)}\s\$+"
NOTE_NUMBER_PATTERN_WITHOUT_CAPTURING_GROUP = r"\$+\s\^\{\d+}\s\$+"


def load_bucket_url_from_env() -> str | None:
    """Load environment variables explicitly for parsing runtime configuration."""
    load_dotenv()
    return os.getenv("FIGURES_BUCKET_URL")


def format_block_number(page_num: int, block_num: int) -> str:
    """Formats block number as '{page_num}:{block_num}'."""
    return f"{page_num}:{block_num}"


class DocumentAssembler:
    def __init__(
        self,
        paddle_dir: str | Path,
        figures_json: str | Path,
        blocks_json: str | Path,
        tables_json: str | Path,
        formulas_json: str | Path,
        figures_bucket_url: str | None = None,
    ) -> None:
        logger.info("[*] Assembler Initialization: Validating Sources...")
        self.paddle_dir = Path(paddle_dir)
        self.figures_json = Path(figures_json)
        self.blocks_json = Path(blocks_json)
        self.tables_json = Path(tables_json)
        self.formulas_json = Path(formulas_json)

        self._validate_files(
            [self.figures_json, self.blocks_json, self.tables_json, self.formulas_json]
        )

        self.paddle_pages = self._load_all_paddle_jsons(self.paddle_dir)
        self.image_map = self._load_and_offset(self.figures_json, "page")
        self.block_map = self._load_and_offset(self.blocks_json, "page")
        self.table_map = self._load_and_offset(self.tables_json, "page_number")
        self.formula_map = self._safe_load_json(self.formulas_json)

        # Blocks are in FITZ space, scale up to Paddle
        kx_b = PADDLE_WIDTH / FITZ_WIDTH
        ky_b = PADDLE_HEIGHT / FITZ_HEIGHT
        self._apply_bbox_transform_to_map(self.block_map, kx_b, ky_b)

        # Images are in pixels (200 DPI), scale to FITZ then to Paddle
        kx_i = (PADDLE_WIDTH / FITZ_WIDTH) * IMAGE_SCALE
        ky_i = (PADDLE_HEIGHT / FITZ_HEIGHT) * IMAGE_SCALE
        self._apply_bbox_transform_to_map(self.image_map, kx_i, ky_i)

        self.meta_extractor = MetadataExtractor()
        self.final_chunks: list[dict[str, Any]] = []
        self._part_index = -1
        self._last_part_title: str | None = None

        self._acc: list[str] = []
        # accumulates image links from paddle blocks to be attached to the next text chunk
        self._acc_links: list[str] = []
        self._acc_start_page: int | None = None
        self._acc_block_ids: list[str] = []
        self._last_numbered_formula_chunks: list[dict[str, Any]] = []
        self._not_captioned_images: list[dict[str, Any]] = []

        self.figures_bucket_url: str | None = None

        if figures_bucket_url:
            self.figures_bucket_url = figures_bucket_url
        else:
            self.figures_bucket_url = load_bucket_url_from_env()

    def _transform_bbox(
        self,
        bbox: list[float],
        kx: float,
        ky: float,
    ) -> list[float]:
        x1, y1, x2, y2 = bbox
        return [x1 * kx, y1 * ky, x2 * kx, y2 * ky]

    def _apply_bbox_transform_to_map(
        self,
        data_map: dict[int, list[dict[str, Any]]],
        kx: float,
        ky: float,
    ) -> None:
        for page_items in data_map.values():
            for item in page_items:
                bbox = item.get("bbox")
                if bbox and len(bbox) == 4:
                    item["bbox"] = self._transform_bbox(bbox, kx, ky)

    def _validate_files(self, file_paths: list[Path]) -> None:
        for path in file_paths:
            if not path.exists():
                logger.error("missing_source", file_path=str(path))
                raise FileNotFoundError(f"Critical data source missing: {path}")

    def _safe_load_json(self, path: str | Path) -> dict[str, Any]:
        """Safely loads a JSON file, returning an empty dict on failure."""
        path = Path(path)
        if not path.exists():
            return {}
        with path.open("r", encoding="utf-8") as f:
            res: dict[str, Any] = json.load(f)
            return res

    def _load_and_offset(
        self, path: Path, page_key: str, offset: int = 0
    ) -> dict[int, list[dict[str, Any]]]:
        data = self._safe_load_json(path)
        if not data:
            return {}
        m: dict[int, list[dict[str, Any]]] = {}
        if isinstance(data, list):
            for item in data:
                try:
                    p_val = item.get(page_key)
                    if p_val is not None:
                        actual_page = int(p_val) + offset
                        m.setdefault(actual_page, []).append(item)
                except (KeyError, ValueError):
                    continue
        return m

    def _load_all_paddle_jsons(self, directory: Path) -> list[dict[str, Any]]:
        combined: list[dict[str, Any]] = []
        if not directory.exists():
            return []

        files = sorted(
            [f for f in directory.iterdir() if f.suffix == ".json"],
            key=lambda f: [
                int(s) if s.isdigit() else s.lower() for s in re.split(r"(\d+)", f.name)
            ],
        )

        for file_path in files:
            data = self._safe_load_json(file_path)
            if isinstance(data, list):
                combined.extend(data)
            else:
                combined.append(data)
        return combined

    def _generate_deterministic_id(
        self, chunk_type: str, entity_id: str | None, content: str
    ) -> str:
        """Generates a stable unique ID for the chunk using SHA-256 (S324)."""
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()[:8]
        prefix = f"{chunk_type}_{entity_id}" if entity_id else chunk_type
        return f"{prefix}_{content_hash}"

    def _update_part_from_doc_title(self, page_data: dict[str, Any], page_num: int) -> None:
        blocks = page_data.get("prunedResult", {}).get("parsing_res_list", [])
        for block in blocks:
            label = block.get("block_label", "").lower()
            if label != "doc_title":
                continue

            raw_title = block.get("block_content", "")
            part_title = raw_title.strip("#").strip()
            if not part_title or part_title == self._last_part_title:
                continue

            if self._acc:
                prev_meta = self.meta_extractor.get_meta().copy()
                self._flush_accumulated_chunk(page_num, prev_meta)

            self._part_index += 1
            part_value = PART_SEQUENCE[min(self._part_index, len(PART_SEQUENCE) - 1)]
            self.meta_extractor.set_part(part_value, part_title)
            self._last_part_title = part_title

            break

    def _flush_accumulated_chunk(self, page_num: int, prev_meta: dict[str, Any]) -> None:
        prev_is_ex = (prev_meta.get("subsection_title") or "").strip().lower() == "exercises"
        e_id = self._extract_id(self._acc[0]) if prev_is_ex else None
        chunk = self._flush(
            self._acc,
            self._acc_start_page or page_num,
            meta_override=prev_meta,
            c_type="exercise" if prev_is_ex else "text",
            entity_id=e_id,
            block_ids=self._acc_block_ids,
        )
        if chunk and chunk["chunk_type"] in ["text", "exercise"]:
            for formula_chunk in self._last_numbered_formula_chunks:
                formula_chunk["defined_in_chunk"] = chunk["chunk_id"]
            self._last_numbered_formula_chunks = []
        self._acc = []
        self._acc_block_ids = []
        self._acc_links = []
        self._acc_start_page = None

    def assemble(self) -> None:
        logger.info(f"[*] Starting assembly of {len(self.paddle_pages)} pages...")
        last_processed_page = START_PAGE
        for page_idx, page_data in enumerate(self.paddle_pages):
            if START_PAGE <= page_idx + 1 <= LAST_PAGE:
                if (page_idx + 1) not in PAGES_NOT_TO_FIX_PADDLE:
                    self._fix_paddle_problems(page_data)
                self._update_part_from_doc_title(page_data, page_idx + 1)
                self._process_page(page_idx, page_data)
                last_processed_page = page_idx + 1

        if self._acc:
            curr_meta = self.meta_extractor.get_meta()
            is_ex_now = (curr_meta.get("subsection_title") or "").strip().lower() == "exercises"
            chunk = self._flush(
                self._acc,
                self._acc_start_page or last_processed_page,
                c_type="exercise" if is_ex_now else "text",
                block_ids=self._acc_block_ids,
            )
            if chunk and chunk["chunk_type"] in ["text", "exercise"]:
                for formula_chunk in self._last_numbered_formula_chunks:
                    formula_chunk["defined_in_chunk"] = chunk["chunk_id"]
                self._last_numbered_formula_chunks = []
            self._acc = []
            self._acc_block_ids = []
            # reset links accumulator after final flush
            self._acc_links = []
            self._acc_start_page = None

        self._save()

    def _fix_paddle_problems(self, page_data: dict[str, Any]) -> None:
        """Sometimes paddleocr moves text of note to random text block. This is partial fix."""
        blocks = page_data.get("prunedResult", {}).get("parsing_res_list", [])
        correct_notes = set()

        for block in blocks:
            content = block.get("block_content", "").strip()
            if match := re.match(rf"^{NOTE_NUMBER_PATTERN}", content):
                number = match.group(1)
                correct_notes.add(number)

        for idx, block in enumerate(blocks):
            if block["block_content"].strip() == "":
                for idx2 in range(idx, -1, -1):
                    content = blocks[idx2].get("block_content", "").strip()
                    if re.search(NOTE_NUMBER_PATTERN, content):
                        results = re.findall(NOTE_NUMBER_PATTERN_WITHOUT_CAPTURING_GROUP, content)
                        if results:
                            result = results[-1]
                            search = re.search(NOTE_NUMBER_PATTERN, result)
                            if search is None:
                                continue
                            number = search.group(1)
                            if number in correct_notes:
                                continue
                            rindex = content.rfind(result)
                            # move note text to note block and remove from original block
                            blocks[idx2]["block_content"] = content[:rindex].strip()
                            blocks[idx]["block_content"] = content[rindex:]
                            break

    def _process_page(self, page_idx: int, page_data: dict[str, Any]) -> None:
        page_num = int(page_data.get("page_num") or (page_idx + 1))

        blocks = page_data.get("prunedResult", {}).get("parsing_res_list", [])

        def sort_by_y_than_x(b: dict[str, Any]) -> tuple[float, float]:
            bbox = b.get("block_bbox", [0, 0, 0, 0])
            return bbox[1], bbox[0]

        # attach notes to correct blocks
        new_blocks = []
        for block in blocks:
            match = re.match(rf"^{NOTE_NUMBER_PATTERN}", block.get("block_content", "").strip())
            if match:
                pattern = r"\$+\s\^\{" + re.escape(match.group(1)) + r"}\s\$+"
                other_block = next(
                    (
                        b
                        for b in blocks
                        if re.search(pattern, b.get("block_content", "").strip()) and b is not block
                    ),
                    None,
                )
                if other_block:
                    other_block["block_content"] += f"\n({block.get('block_content', '').strip()})"
                else:
                    new_blocks.append(block)
            else:
                new_blocks.append(block)
        blocks = new_blocks
        blocks = sorted(blocks, key=sort_by_y_than_x)

        if not blocks:
            return
        used_indices: set[int] = set()

        used_indices.update(self._handle_images(page_num, blocks))
        special_accs = self._handle_text_stream(page_num, blocks, used_indices)

        for (eid, ctype), data in special_accs.items():
            full_text = "\n".join(data["content"])
            meta = self.meta_extractor.process_content_and_get_meta(full_text, update_meta=False)
            chunk = self._create_chunk_obj(
                data["chunk_type"], full_text, page_num, meta, data["block_ids"], entity_id=eid
            )

            if "formula_chunks" in data:
                for formula_chunk in data["formula_chunks"]:
                    formula_chunk["defined_in_chunk"] = chunk["chunk_id"]

            # extend chunk links with links captured from paddle blocks in special region
            chunk["image_links"].extend(data.get("image_links", []))

            for img_chunk in list(self._not_captioned_images):
                if (
                    img_chunk.get("entity_id") == eid
                    and img_chunk.get("chunk_type", "").lower() == ctype.lower()
                ):
                    chunk["image_links"].append(
                        f"{FIGURES_BUCKET_URL}figures/figure_{img_chunk['image_index']-1}.png"
                    )
                    self._not_captioned_images.remove(img_chunk)

            self.final_chunks.append(chunk)

    def _handle_images(
        self,
        page_num: int,
        blocks: list[dict[str, Any]],
    ) -> set[int]:
        used: set[int] = set()
        used_block_ids: set[int] = set()
        visual_items = self.image_map.get(page_num, [])
        captioned_images = []

        for eid, v_obj in zip(
            (v.get("entity_id") for v in visual_items), visual_items, strict=False
        ):
            # attach link to the closest valid paddle block above if this is a text figure
            if v_obj.get("chunk_type") == "text" and "image_index" in v_obj:
                v_y, target_block = v_obj.get("bbox", [0, 0, 0, 0])[1], None
                for b in blocks:
                    if b.get("block_label", "").lower() in PADDLE_BLOCKS_TO_SKIP:
                        continue
                    if b.get("block_bbox", [0, 0, 0, 0])[1] < v_y:
                        target_block = b
                    else:
                        break
                if target_block:
                    target_block.setdefault("image_links", []).append(
                        f"{FIGURES_BUCKET_URL}figures/figure_{v_obj['image_index']-1}.png"
                    )

            clean_content = v_obj.get("caption", v_obj.get("content", "")).strip()

            entity_number = self._extract_id(clean_content, full=True)
            block_id = None
            for idx, block in enumerate(blocks):
                bbox = block.get("block_bbox")
                if bbox and self._is_inside(bbox, v_obj.get("bbox", [])):
                    used.add(idx)
                    used_block_ids.add(block["block_id"])

                if entity_number in block.get("block_content", ""):
                    block_id = format_block_number(page_num, block["block_id"])

            meta_res = self.meta_extractor.process_content_and_get_meta(clean_content)
            formated_used = [format_block_number(page_num, idx) for idx in used_block_ids]
            chunk_block_ids = formated_used.copy()
            if block_id is not None:
                chunk_block_ids.append(block_id)
            chunk = self._create_chunk_obj(
                v_obj["chunk_type"].lower(),
                clean_content,
                page_num,
                meta_res,
                chunk_block_ids,
                entity_id=eid,
            )

            if "image_index" in v_obj:
                img_link = f"{FIGURES_BUCKET_URL}figures/figure_{v_obj['image_index']-1}.png"
                chunk["image_links"] = [img_link]

                if eid and v_obj.get("chunk_type", "").lower() == "exercise":
                    existing = next(
                        (
                            c
                            for c in self.final_chunks
                            if c.get("entity_id") == eid and c.get("chunk_type") == "exercise"
                        ),
                        None,
                    )
                    if existing:
                        existing["image_links"].append(img_link)
                        # skip adding a separate chunk for this image because
                        # it's already linked to the exercise chunk
                        continue

            if chunk["chunk_type"] == "captioned_image":
                captioned_images.append(chunk)
            else:
                self._not_captioned_images.append(v_obj)

        # deduplicate captioned images by entity_id, merging image links if necessary
        for img_chunk in captioned_images:
            existing = next(
                (c for c in captioned_images if c.get("entity_id") == img_chunk["entity_id"]), None
            )
            if existing and existing is not img_chunk:
                existing["image_links"].extend(img_chunk.get("image_links", []))
            else:
                self.final_chunks.append(img_chunk)
        return used

    def _handle_text_stream(
        self, page_num: int, blocks: list[dict[str, Any]], used_indices: set[int]
    ) -> dict[tuple[str | None, str], dict[str, Any]]:
        special_regions = self.block_map.get(page_num, [])
        special_accs: dict[tuple[str | None, str], dict[str, Any]] = {
            (sr.get("entity_id"), str(sr.get("chunk_type", "")).lower()): {
                **sr,
                "content": [sr.get("caption", "")],
                "chunk_type": str(sr.get("chunk_type", "")).lower(),
            }
            for sr in special_regions
        }

        for idx, block in enumerate(blocks):
            if idx in used_indices:
                continue
            content = block.get("block_content", "").strip()
            label = block.get("block_label", "").lower()
            if label in PADDLE_BLOCKS_TO_SKIP:
                continue

            matched_key = None
            bbox = block.get("block_bbox")
            if bbox:
                for sr in special_regions:
                    if self._is_inside(bbox, sr.get("bbox", [])):
                        matched_key = (
                            sr.get("entity_id"),
                            str(sr.get("chunk_type", "")).lower(),
                        )
                        break

            text = BeautifulSoup(content, "html.parser").get_text().strip().lower()
            if match := re.search(r"^(example|algorithm|figure|table)\s+([a-z\d]+\.\d+)\.", text):
                # this is caption, it will be added to corresponding
                # numbered entity chunk, ignore here
                match_str = match.group(0)
                split = match_str.split(" ")
                key = (split[1][:-1].upper(), split[0])  # (number, type)
                if special_block := special_accs.get(key):
                    special_block.setdefault("block_ids", []).append(
                        format_block_number(page_num, block["block_id"])
                    )
                continue

            # Capture hierarchy state before processing the current block.
            prev_meta = self.meta_extractor.get_meta().copy()
            temp_meta = self.meta_extractor.process_content_and_get_meta(content)

            is_ex_sub = (temp_meta.get("subsection_title") or "").strip().lower() == "exercises"
            is_new_ex = bool(re.match(r"^#*\s*Exercise\s+\d+\.\d+", text, re.I))

            if temp_meta.get("force_new_chunk") and self._acc:
                self._flush_accumulated_chunk(page_num, prev_meta)

            if label == "table":
                was_numbered_table = self._process_table(
                    content, page_num, temp_meta, format_block_number(page_num, block["block_id"])
                )
                if was_numbered_table:
                    continue

            if label == "formula_number" and content in self.formula_map:
                formula_id = content[1:-1]  # Remove parentheses
                f_chunk = self._add_formula_chunk(
                    formula_id,
                    page_num,
                    format_block_number(
                        page_num, block["block_id"] - 1
                    ),  # formulas are usually right above the block that references them
                )
                if matched_key:
                    special_accs[matched_key].setdefault("formula_chunks", []).append(f_chunk)
                    special_accs[matched_key].setdefault("block_ids", []).append(
                        format_block_number(page_num, block["block_id"])
                    )
                else:
                    self._last_numbered_formula_chunks.append(f_chunk)

            if content:
                # capture image links from paddle block if present
                block_links = block.get("image_links", [])
                if matched_key:
                    special_accs[matched_key].setdefault("image_links", []).extend(block_links)
                    special_accs[matched_key]["content"].append(content)
                    special_accs[matched_key].setdefault("block_ids", []).append(
                        format_block_number(page_num, block["block_id"])
                    )
                else:
                    split_on_ex = is_ex_sub and is_new_ex and self._acc
                    split_on_len = (
                        not is_ex_sub
                        and self._acc
                        and len("\n".join(self._acc + [content])) > MAX_CHUNK_CHAR_LENGTH
                    )

                    if split_on_ex or split_on_len:
                        e_id = self._extract_id(self._acc[0]) if is_ex_sub else None
                        chunk = self._flush(
                            self._acc,
                            self._acc_start_page or page_num,
                            c_type="exercise" if is_ex_sub else "text",
                            entity_id=e_id,
                            block_ids=self._acc_block_ids,
                        )
                        if chunk and chunk["chunk_type"] in ["text", "exercise"]:
                            for formula_chunk in self._last_numbered_formula_chunks:
                                formula_chunk["defined_in_chunk"] = chunk["chunk_id"]
                            self._last_numbered_formula_chunks = []
                        self._acc = []
                        self._acc_block_ids = []
                        # reset links accumulator after flush
                        self._acc_links = []
                        self._acc_start_page = None

                    if not self._acc:
                        self._acc_start_page = page_num
                    self._acc.append(content)
                    self._acc_block_ids.append(format_block_number(page_num, block["block_id"]))
                    # accumulate links for normal text chunks
                    self._acc_links.extend(block_links)

        return special_accs

    def _process_table(
        self, content: str, page_num: int, temp_meta: dict[str, Any], block_id: str
    ) -> bool:
        for possible_table in self.table_map.get(page_num, []):
            if clean_html_attributes(content) == possible_table["table_content"].strip():
                caption = re.sub("<[^<]+?>", "", possible_table.get("caption_content", ""))
                e_id = self._extract_id(caption)
                chunk = self._create_chunk_obj(
                    "numbered_table",
                    clean_html_attributes(content),
                    page_num,
                    temp_meta,
                    [block_id],
                    entity_id=e_id,
                )
                chunk.update(
                    {
                        "content": caption + "\n" + chunk["content"],
                    }
                )
                if hasattr(self.meta_extractor, "get_references"):
                    chunk.update(self.meta_extractor.get_references(chunk["content"]))
                self.final_chunks.append(chunk)
                return True
        return False

    def _add_formula_chunk(self, f_id: str, page_num: int, block_id: str) -> dict[str, Any]:
        meta_now = self.meta_extractor.get_meta()
        formula_content = self.formula_map.get(f"({f_id})", f"Formula {f_id}")
        f_chunk = self._create_chunk_obj(
            "numbered_formula", formula_content, page_num, meta_now, [block_id], entity_id=f_id
        )
        self.final_chunks.append(f_chunk)
        return f_chunk

    def _create_chunk_obj(
        self,
        c_type: str,
        content: str,
        page: int,
        meta: dict[str, Any],
        block_ids: list[str],
        entity_id: str | None = None,
    ) -> dict[str, Any]:
        final_type = "exercise" if meta.get("is_exercise") or c_type == "exercise" else c_type
        extracted_id = entity_id or self._extract_id(content)
        if final_type in ["exercise", "example", "algorithm", "captioned_image", "numbered_table"]:
            content = re.sub(
                r"^(Exercise|Figure|Table|Algorithm|Example)\s+\d+\.\d+\.", "", content, flags=re.I
            ).strip()

        chunk: dict[str, Any] = {
            "chunk_id": self._generate_deterministic_id(
                final_type, meta.get("subsubsection_number"), content
            ),
            "entity_id": extracted_id,
            "part": meta.get("part"),
            "part_title": meta.get("part_title"),
            "section_title": meta.get("section_title"),
            "section_number": meta.get("section_number"),
            "subsection_title": meta.get("subsection_title"),
            "subsection_number": meta.get("subsection_number"),
            "subsubsection_title": meta.get("subsubsection_title"),
            "subsubsection_number": meta.get("subsubsection_number"),
            "chunk_type": final_type,
            "content": content,
            "page": page,
            "image_links": [],
            "pdf_block_ids": block_ids,
        }

        if hasattr(self.meta_extractor, "get_references"):
            chunk.update(self.meta_extractor.get_references(content))

        if (
            chunk["chunk_type"] == "exercise"
            and chunk.get("entity_id")
            and "referenced_exercises" in chunk
        ):
            ref_exercises = chunk.get("referenced_exercises")
            if isinstance(ref_exercises, list):
                with contextlib.suppress(ValueError, KeyError):
                    ref_exercises.remove(chunk["entity_id"])
        return chunk

    def _is_inside(self, b1: list[float], b2: list[float]) -> bool:
        if not b1 or not b2 or len(b1) < 4 or len(b2) < 4:
            return False
        return (
            b1[0] >= b2[0] - BBOX_PADDING
            and b1[1] >= b2[1] - BBOX_PADDING
            and b1[2] <= b2[2] + BBOX_PADDING
            and b1[3] <= b2[3] + BBOX_PADDING
        )

    def _flush(
        self,
        acc: list[str],
        page: int,
        meta_override: dict[str, Any] | None = None,
        c_type: str = "text",
        entity_id: str | None = None,
        block_ids: list[str] | None = None,
    ) -> dict[str, Any] | None:
        raw_text = "\n".join(acc)
        meta_res = self.meta_extractor.process_content_and_get_meta(raw_text, update_meta=False)

        if meta_override is not None:
            for key in (
                "part",
                "part_title",
                "section_title",
                "section_number",
                "subsection_title",
                "subsection_number",
                "subsubsection_title",
                "subsubsection_number",
            ):
                meta_res[key] = meta_override.get(key)

        is_part_chunk = re.match(r"^PART\s[IV]+$", meta_res["clean_content"].strip())
        if not meta_res["clean_content"] or is_part_chunk:
            return None
        safe_block_ids = block_ids or []
        chunk = self._create_chunk_obj(
            c_type, meta_res["clean_content"], page, meta_res, safe_block_ids, entity_id=entity_id
        )
        # add links accumulated from paddle blocks in normal text stream
        chunk["image_links"].extend(self._acc_links)

        if chunk["chunk_type"] == "exercise" and chunk.get("entity_id"):
            eid = chunk["entity_id"]
            for img_chunk in list(self._not_captioned_images):
                if (
                    img_chunk.get("entity_id") == eid
                    and img_chunk.get("chunk_type", "").lower() == "exercise"
                ):
                    chunk["image_links"].append(
                        f"{FIGURES_BUCKET_URL}figures/figure_{img_chunk['image_index']-1}.png"
                    )
                    self._not_captioned_images.remove(img_chunk)

        self.final_chunks.append(chunk)
        return chunk

    def _extract_id(self, text: str | None, full: bool = False) -> str | None:
        if not text:
            return None
        # Спочатку шукаємо за суворим шаблоном
        m = re.search(
            r"(?:Exercise|Figure|Table|Algorithm|Example)\s+([a-zA-Z\d]+\.\d+)", str(text), re.I
        )
        if not m:
            # Якщо не знайшли, шукаємо просто число формату X.X (наприклад, "4.4")
            m = re.search(r"\b([a-zA-Z\d]+\.\d+)\b", str(text))

        if m:
            return m.group(0) if full else m.group(1)
        return None

    def _save(self) -> None:
        output = Path("ULTIMATE_BOOK_DATA.json")
        with output.open("w", encoding="utf-8") as f:
            json.dump(self.final_chunks, f, indent=2, ensure_ascii=False)
        logger.info(f"\n[SUCCESS] Saved {len(self.final_chunks)} logical chunks.")


if __name__ == "__main__":
    base = Path("data_source")
    assembler = DocumentAssembler(
        paddle_dir=base / "paddle_results",
        figures_json=base / "figures_metadata.json",
        blocks_json=base / "blocks_metadata.json",
        tables_json=base / "extracted_tables.json",
        formulas_json=base / "formula_mapping.json",
    )
    assembler.assemble()
