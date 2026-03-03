import hashlib
import json
import re
from pathlib import Path
from typing import Any

from common.logging import configure_logging, get_logger

try:
    from .metadata_extractor import MetadataExtractor
except ImportError:
    from metadata_extractor import MetadataExtractor  # type: ignore

configure_logging("rag-service", log_level="INFO")
logger = get_logger(__name__)

logger.info("service_started", message="RAG Service is up and running")

PAGE_OFFSET = 18
BBOX_PADDING = 35
ID_PREFIX_LIMIT = 100


class DocumentAssembler:
    def __init__(
        self,
        paddle_dir: str | Path,
        figures_json: str | Path,
        blocks_json: str | Path,
        tables_json: str | Path,
        formulas_json: str | Path,
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
        self.image_map = self._load_and_offset(self.figures_json, "page", offset=PAGE_OFFSET)
        self.block_map = self._load_and_offset(self.blocks_json, "page", offset=0)
        self.table_map = self._load_and_offset(self.tables_json, "page", offset=0)
        self.formula_map = self._safe_load_json(self.formulas_json)

        self.meta_extractor = MetadataExtractor()
        self.final_chunks: list[dict[str, Any]] = []

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

    def assemble(self) -> None:
        logger.info(f"[*] Starting assembly of {len(self.paddle_pages)} pages...")
        for page_idx, page_data in enumerate(self.paddle_pages):
            self._process_page(page_idx, page_data)
        self._save()

    def _process_page(self, page_idx: int, page_data: dict[str, Any]) -> None:
        page_num = int(page_data.get("page_num") or (page_idx + 1))

        markdown_data = page_data.get("markdown", {})
        full_markdown_text = markdown_data.get("text", "")

        if full_markdown_text:
            meta_res = self.meta_extractor.process_content_and_get_meta(full_markdown_text)
            chunk = self._create_chunk_obj("text", full_markdown_text, page_num, meta_res)

            if hasattr(self.meta_extractor, "get_references"):
                refs = self.meta_extractor.get_references(full_markdown_text)
                chunk.update(refs)

            self.final_chunks.append(chunk)
            logger.info(f"Page {page_num}: Processed using high-quality Markdown.")
            return

        blocks = page_data.get("prunedResult", {}).get("parsing_res_list", [])
        if not blocks:
            return
        used_indices: set[int] = set()
        used_indices.update(self._handle_visual_objects(page_num, blocks))
        self._handle_tables(page_num)
        self._handle_text_stream(page_num, blocks, used_indices)

    def _handle_visual_objects(self, page_num: int, blocks: list[dict[str, Any]]) -> set[int]:
        used: set[int] = set()
        visual_items = self.block_map.get(page_num, []) + self.image_map.get(page_num, [])
        merged_visuals = self._merge_visual_items(visual_items)

        for eid, v_obj in merged_visuals.items():
            for idx, block in enumerate(blocks):
                bbox = block.get("block_bbox")
                if bbox and self._is_inside(bbox, v_obj.get("bbox", [])):
                    used.add(idx)

            full_caption = v_obj.get("caption", v_obj.get("content", ""))
            clean_content = (
                full_caption.replace("[BLOCK EXERCISE CONTENT]:", "")
                .replace("[BLOCK EXAMPLE CONTENT]:", "")
                .strip()
            )

            meta_res = self.meta_extractor.process_content_and_get_meta(clean_content)
            chunk = self._create_chunk_obj(v_obj["chunk_type"], clean_content, page_num, meta_res)

            chunk.update({"entity_id": eid, "caption": full_caption})

            if "image_index" in v_obj:
                chunk["image_links"] = [f"images/fig_{v_obj['image_index']}.png"]

            self.final_chunks.append(chunk)
        return used

    def _merge_visual_items(self, items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        merged: dict[str, dict[str, Any]] = {}
        for item in items:
            eid = item.get("entity_id") or self._extract_id(item.get("caption", ""))
            if eid is None:
                continue
            if eid not in merged:
                merged[eid] = item
            else:
                if "image_index" in item:
                    merged[eid]["image_index"] = item["image_index"]
                if (
                    "bbox" in item
                    and isinstance(item["bbox"], (list, tuple))
                    and len(item["bbox"]) == 4
                ):
                    b2 = item["bbox"]
                    b1 = merged[eid].get("bbox")

                    if b1 and isinstance(b1, (list, tuple)) and len(b1) == 4:
                        merged[eid]["bbox"] = [
                            min(b1[0], b2[0]),
                            min(b1[1], b2[1]),
                            max(b1[2], b2[2]),
                            max(b1[3], b2[3]),
                        ]
                    else:
                        merged[eid]["bbox"] = list(b2)
        return merged

    def _handle_text_stream(
        self, page_num: int, blocks: list[dict[str, Any]], used_indices: set[int]
    ) -> None:
        acc: list[str] = []
        for idx, block in enumerate(blocks):
            if idx in used_indices:
                continue
            content = block.get("block_content", "").strip()
            label = block.get("block_label", "").lower()

            temp_meta = self.meta_extractor.process_content_and_get_meta(content)
            if temp_meta.get("force_new_chunk") and acc:
                self._flush(acc, page_num)
                acc = []

            f_match = re.search(r"\((\d+\.\d+)\)", content)
            if f_match:
                formula_key = f_match.group(0)
                formula_id = f_match.group(1)

                if formula_key in self.formula_map:
                    if acc:
                        self._flush(acc, page_num)
                        acc.clear()

                    self._add_formula_chunk(formula_id, page_num)

            if label in ["header", "title"] and acc:
                self._flush(acc, page_num)
                acc = []

            if content and label not in ["footer", "number"]:
                acc.append(content)
        if acc:
            self._flush(acc, page_num)

    def _add_formula_chunk(self, f_id: str, page_num: int) -> None:
        meta_now = self.meta_extractor.process_content_and_get_meta("")
        formula_content = self.formula_map.get(f"({f_id})", f"Formula {f_id}")
        f_chunk = self._create_chunk_obj("numbered_formula", formula_content, page_num, meta_now)
        f_chunk["link_id"] = f_id
        self.final_chunks.append(f_chunk)

    def _handle_tables(self, page_num: int) -> None:
        if page_num in self.table_map:
            for tbl in self.table_map[page_num]:
                caption = re.sub("<[^<]+?>", "", tbl.get("caption_content", ""))
                meta_res = self.meta_extractor.process_content_and_get_meta(
                    tbl.get("table_content", "")
                )
                chunk = self._create_chunk_obj(
                    "numbered_table", meta_res["clean_content"], page_num, meta_res
                )
                chunk.update({"entity_id": self._extract_id(caption), "caption": caption})
                self.final_chunks.append(chunk)

    def _create_chunk_obj(
        self, c_type: str, content: str, page: int, meta: dict[str, Any]
    ) -> dict[str, Any]:
        final_type = "exercise" if meta.get("is_exercise") or c_type == "exercise" else c_type

        return {
            "chunk_id": self._generate_deterministic_id(
                final_type, meta.get("subsubsection_number"), content
            ),
            "entity_id": meta.get("subsubsection_number") or self._extract_id(content),
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

    def _flush(self, acc: list[str], page: int) -> None:
        raw_text = "\n".join(acc)
        meta_res = self.meta_extractor.process_content_and_get_meta(raw_text)
        if not meta_res.get("clean_content"):
            return
        chunk = self._create_chunk_obj("text", meta_res["clean_content"], page, meta_res)
        if hasattr(self.meta_extractor, "get_references"):
            refs = self.meta_extractor.get_references(meta_res["clean_content"])
            chunk.update(refs)
        self.final_chunks.append(chunk)

    def _extract_id(self, text: str | None) -> str | None:
        if not text:
            return None
        m = re.search(r"(?:Exercise|Figure|Table|Algorithm|Example)\s+(\d+\.\d+)", str(text), re.I)
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
