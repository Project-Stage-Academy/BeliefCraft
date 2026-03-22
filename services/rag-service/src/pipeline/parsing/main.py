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

PAGE_OFFSET = 18
START_PAGE = 23
LAST_PAGE = 648
BBOX_PADDING = 5
MAX_CHUNK_CHAR_LENGTH = 1000

ID_PREFIX_LIMIT = 100
PART_SEQUENCE = ["I", "II", "III", "IV", "V", "Appendices"]
IMAGE_SCALE = 0.36  # 72 points per inch / 200 dpi
FITZ_WIDTH = 576
FITZ_HEIGHT = 648
PADDLE_WIDTH = 1152
PADDLE_HEIGHT = 1296


def load_bucket_url_from_env() -> str | None:
    """Load environment variables explicitly for parsing runtime configuration."""
    load_dotenv()
    return os.getenv("FIGURES_BUCKET_URL")


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
        self.image_map = self._load_and_offset(self.figures_json, "page", offset=0)
        self.block_map = self._load_and_offset(self.blocks_json, "page", offset=0)
        self.table_map = self._load_and_offset(self.tables_json, "page_number", offset=0)
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

    def _update_part_from_doc_title(self, page_data: dict[str, Any]) -> None:
        blocks = page_data.get("prunedResult", {}).get("parsing_res_list", [])
        for block in blocks:
            label = block.get("block_label", "").lower()
            if label != "doc_title":
                continue

            raw_title = block.get("block_content", "")
            part_title = raw_title.strip("#").strip()
            if not part_title or part_title == self._last_part_title:
                continue

            self._part_index += 1
            part_value = PART_SEQUENCE[min(self._part_index, len(PART_SEQUENCE) - 1)]
            self.meta_extractor.set_part(part_value, part_title)
            self._last_part_title = part_title

            break

    def assemble(self) -> None:
        logger.info(f"[*] Starting assembly of {len(self.paddle_pages)} pages...")
        for page_idx, page_data in enumerate(self.paddle_pages):
            if START_PAGE <= page_idx + 1 <= LAST_PAGE:
                self._update_part_from_doc_title(page_data)
                self._process_page(page_idx, page_data)
        self._save()

    def _process_page(self, page_idx: int, page_data: dict[str, Any]) -> None:
        page_num = int(page_data.get("page_num") or (page_idx + 1))

        blocks = page_data.get("prunedResult", {}).get("parsing_res_list", [])

        def sort_by_height(b: dict[str, Any]) -> float:
            return b.get("block_bbox", [0, 0, 0, 0])[1] if b.get("block_bbox") else 0

        blocks = sorted(blocks, key=sort_by_height)

        if not blocks:
            return
        used_indices: set[int] = set()

        not_captioned_images: list[dict[str, Any]] = []
        used_indices.update(self._handle_images(page_num, blocks, not_captioned_images))
        special_accs = self._handle_text_stream(page_num, blocks, used_indices)

        for (eid, _), data in special_accs.items():
            full_text = "\n".join(data["content"])
            meta = self.meta_extractor.process_content_and_get_meta(full_text, update_meta=False)
            chunk = self._create_chunk_obj(data["chunk_type"], full_text, page_num, meta)
            chunk["entity_id"] = eid

            for img_chunk in list(not_captioned_images):
                if (
                    img_chunk.get("entity_id") == eid
                    and img_chunk.get("chunk_type", "").lower() == data["chunk_type"]
                ):
                    chunk["image_links"].append(
                        f"{FIGURES_BUCKET_URL}figures/figure_{img_chunk['image_index']-1}.png"
                    )
                    not_captioned_images.remove(img_chunk)

            self.final_chunks.append(chunk)

    def _handle_images(
        self,
        page_num: int,
        blocks: list[dict[str, Any]],
        not_captioned_images: list[dict[str, Any]],
    ) -> set[int]:
        used: set[int] = set()
        visual_items = self.image_map.get(page_num, [])
        captioned_images = []

        for eid, v_obj in zip(
            (v.get("entity_id") for v in visual_items), visual_items, strict=False
        ):
            for idx, block in enumerate(blocks):
                bbox = block.get("block_bbox")
                if bbox and self._is_inside(bbox, v_obj.get("bbox", [])):
                    used.add(idx)

            clean_content = v_obj.get("caption", v_obj.get("content", "")).strip()

            meta_res = self.meta_extractor.process_content_and_get_meta(clean_content)
            chunk = self._create_chunk_obj(
                v_obj["chunk_type"].lower(), clean_content, page_num, meta_res
            )

            chunk.update({"entity_id": eid})

            if "image_index" in v_obj:
                chunk["image_links"] = [
                    f"{FIGURES_BUCKET_URL}figures/figure_{v_obj['image_index']-1}.png"
                ]

            if chunk["chunk_type"] == "captioned_image":
                captioned_images.append(chunk)
            else:
                not_captioned_images.append(v_obj)

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
        acc: list[str] = []
        special_regions = self.block_map.get(page_num, [])
        special_accs: dict[tuple[str | None, str], dict[str, Any]] = {
            (sr.get("entity_id"), str(sr.get("chunk_type", "")).lower()): {
                **sr,
                "content": [sr.get("caption", "")],
                "chunk_type": str(sr.get("chunk_type", "")).lower(),
            }
            for sr in special_regions
        }

        last_numbered_formula_chunks = []

        for idx, block in enumerate(blocks):
            if idx in used_indices:
                continue
            content = block.get("block_content", "").strip()
            label = block.get("block_label", "").lower()
            if label in ["footer", "number", "header", "image", "footnote", "doc_title"]:
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
            if re.search(r"^(example|algorithm|figure|table)\s+([a-z\d]+\.\d+)\.", text):
                # this is caption, it will be added to corresponding
                # numbered entity chunk, ignore here
                continue

            # Capture hierarchy state before processing the current block.
            prev_meta = self.meta_extractor.get_meta()
            temp_meta = self.meta_extractor.process_content_and_get_meta(content)
            if temp_meta.get("force_new_chunk") and acc:
                self._flush(acc, page_num, meta_override=prev_meta)
                acc = []

            if label == "table":
                was_numbered_table = self._process_table(content, page_num, temp_meta)
                if was_numbered_table:
                    continue

            if label == "formula_number" and content in self.formula_map:
                formula_id = content[1:-1]  # Remove parentheses
                last_numbered_formula_chunks.append(self._add_formula_chunk(formula_id, page_num))

            if content:
                if matched_key:
                    special_accs[matched_key]["content"].append(content)
                else:
                    if acc and len("\n".join(acc + [content])) > MAX_CHUNK_CHAR_LENGTH:
                        chunk = self._flush(acc, page_num)
                        if chunk and chunk["chunk_type"] == "text":
                            for formula_chunk in last_numbered_formula_chunks:
                                formula_chunk["defined_in_chunk"] = chunk["chunk_id"]
                            last_numbered_formula_chunks = []
                        acc = []
                    acc.append(content)
        if acc:
            chunk = self._flush(acc, page_num)
            if chunk and chunk["chunk_type"] == "text":
                for formula_chunk in last_numbered_formula_chunks:
                    formula_chunk["defined_in_chunk"] = chunk["chunk_id"]
        return special_accs

    def _process_table(self, content: str, page_num: int, temp_meta: dict[str, Any]) -> bool:
        for possible_table in self.table_map.get(page_num, []):
            if clean_html_attributes(content) == possible_table["table_content"].strip():
                caption = re.sub("<[^<]+?>", "", possible_table.get("caption_content", ""))
                chunk = self._create_chunk_obj(
                    "numbered_table", clean_html_attributes(content), page_num, temp_meta
                )
                chunk.update(
                    {
                        "entity_id": self._extract_id(caption),
                        "content": caption + "\n" + chunk["content"],
                    }
                )
                self.final_chunks.append(chunk)
                return True
        return False

    def _add_formula_chunk(self, f_id: str, page_num: int) -> dict[str, Any]:
        meta_now = self.meta_extractor.get_meta()
        formula_content = self.formula_map.get(f"({f_id})", f"Formula {f_id}")
        f_chunk = self._create_chunk_obj("numbered_formula", formula_content, page_num, meta_now)
        f_chunk["entity_id"] = f_id
        self.final_chunks.append(f_chunk)
        return f_chunk

    def _create_chunk_obj(
        self, c_type: str, content: str, page: int, meta: dict[str, Any]
    ) -> dict[str, Any]:
        final_type = "exercise" if meta.get("is_exercise") or c_type == "exercise" else c_type

        return {
            "chunk_id": self._generate_deterministic_id(
                final_type, meta.get("subsubsection_number"), content
            ),
            "entity_id": self._extract_id(content),
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
        }

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
        chunk = self._create_chunk_obj("text", meta_res["clean_content"], page, meta_res)
        if hasattr(self.meta_extractor, "get_references"):
            refs = self.meta_extractor.get_references(meta_res["clean_content"])
            chunk.update(refs)
        self.final_chunks.append(chunk)
        return chunk

    def _extract_id(self, text: str | None) -> str | None:
        if not text:
            return None
        # Спочатку шукаємо за суворим шаблоном
        m = re.search(
            r"(?:Exercise|Figure|Table|Algorithm|Example)\s+([a-zA-Z\d]+\.\d+)", str(text), re.I
        )
        if not m:
            # Якщо не знайшли, шукаємо просто число формату X.X (наприклад, "4.4")
            m = re.search(r"\b([a-zA-Z\d]+\.\d+)\b", str(text))
        return m.group(1) if m else None

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
