import json
import os
import re
import hashlib
import logging
from common.logging import configure_logging, get_logger
from metadata_extractor import MetadataExtractor

# Initialize structured logging
configure_logging("rag-service", log_level="INFO")
logger = get_logger(__name__)

# Constants
PAGE_OFFSET = 18 
BBOX_PADDING = 35

class DocumentAssembler:
    """
    Assembles a structured document from various metadata sources including 
    text blocks, images, tables, and formulas.
    """
    def __init__(self, paddle_dir, figures_json, blocks_json, tables_json, formulas_json):
        logger.info("assembler_init", status="validating_sources")
        self._validate_files([figures_json, blocks_json, tables_json, formulas_json])
        
        self.paddle_pages = self._load_all_paddle_jsons(paddle_dir)
        self.image_map = self._load_and_offset(figures_json, "page")
        self.block_map = self._load_and_offset(blocks_json, "page")
        self.table_map = self._load_and_offset(tables_json, "page_number")
        self.formula_map = self._safe_load_json(formulas_json)

        self.meta_extractor = MetadataExtractor()
        self.final_chunks = []

    def _validate_files(self, file_paths):
        """Ensures all required input metadata files exist."""
        for path in file_paths:
            if not os.path.exists(path):
                logger.error("missing_source", file_path=path)
                raise FileNotFoundError(f"Critical data source missing: {path}")

    def _safe_load_json(self, path):
        """Safely loads a JSON file, returning an empty dict on failure."""
        if not os.path.exists(path): 
            return {}
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.warning("json_load_failed", file_path=path, error=str(e))
            return {}

    def _load_and_offset(self, path, page_key):
        """Loads JSON data and applies page numbering offset with validation."""
        data = self._safe_load_json(path)
        if not data: return {}
        m = {}
        for item in data:
            try:
                p_val = item.get(page_key)
                if p_val is not None:
                    actual_page = int(p_val) + PAGE_OFFSET
                    m.setdefault(actual_page, []).append(item)
            except (KeyError, ValueError, TypeError) as e: 
                # Fixed: Added warning logging for data quality issues
                logger.warning("page_offset_error", item=str(item), error=str(e))
                continue
        return m

    def _load_all_paddle_jsons(self, directory):
        """Combines all page-level parsing results from a directory."""
        combined = []
        if not os.path.exists(directory): 
            return []
        files = sorted([f for f in os.listdir(directory) if f.endswith('.json')],
                       key=lambda f: [int(s) if s.isdigit() else s.lower() for s in re.split(r'(\d+)', f)])
        for file_name in files:
            path = os.path.join(directory, file_name)
            data = self._safe_load_json(path)
            if data:
                combined.extend(data if isinstance(data, list) else [data])
        return combined

    def assemble(self):
        """Triggers the assembly process for the entire document."""
        logger.info("assembly_started", page_count=len(self.paddle_pages))
        for page_idx, page_data in enumerate(self.paddle_pages):
            self._process_page(page_idx, page_data)
        self._save()

    def _process_page(self, page_idx, page_data):
        """Processes a single page and its associated objects."""
        page_num = int(page_data.get("page_num") or (page_idx + 1))
        blocks = page_data.get("prunedResult", {}).get("parsing_res_list", [])
        if not blocks: return
        
        used_indices = set()
        used_indices.update(self._handle_visual_objects(page_num, blocks))
        self._handle_tables(page_num)
        self._handle_text_stream(page_num, blocks, used_indices)

    def _handle_visual_objects(self, page_num, blocks):
        """Identifies and chunks figures and special blocks based on spatial overlap."""
        used = set()
        visual_items = self.block_map.get(page_num, []) + self.image_map.get(page_num, [])
        merged_visuals = self._merge_visual_items(visual_items)
        
        for eid, v_obj in merged_visuals.items():
            for idx, block in enumerate(blocks):
                bbox = block.get("block_bbox")
                # Fixed: Added length validation for bbox
                if bbox and len(bbox) == 4 and self._is_inside(bbox, v_obj.get("bbox", [])):
                    used.add(idx)

            full_caption = v_obj.get("caption", v_obj.get("content", ""))
            clean_content = full_caption.replace("[BLOCK EXERCISE CONTENT]:", "").replace("[BLOCK EXAMPLE CONTENT]:", "").strip()
            
            meta_res = self.meta_extractor.process_content_and_get_meta(clean_content)
            chunk = self._create_chunk_obj(v_obj["chunk_type"], clean_content, page_num, meta_res)
            
            chunk.update({"entity_id": eid, "caption": full_caption})
            if "image_index" in v_obj:
                chunk["image_links"] = [f"images/fig_{v_obj['image_index']}.png"]
            
            self.final_chunks.append(chunk)
        return used

    def _merge_visual_items(self, items):
        """Merges duplicate or related visual metadata entries for the same ID."""
        merged = {}
        for item in items:
            eid = item.get("entity_id") or self._extract_id(item.get("caption", ""))
            if eid is None: continue
            
            if eid not in merged: 
                merged[eid] = item
            else:
                if "image_index" in item: 
                    merged[eid]["image_index"] = item["image_index"]
                
                # Fixed: Added validation for merging bboxes
                if "bbox" in item and len(item["bbox"]) == 4:
                    b1 = merged[eid].get("bbox", [])
                    b2 = item["bbox"]
                    if len(b1) == 4:
                        merged[eid]["bbox"] = [min(b1[0], b2[0]), min(b1[1], b2[1]), max(b1[2], b2[2]), max(b1[3], b2[3])]
                    else:
                        merged[eid]["bbox"] = b2
        return merged

    def _handle_text_stream(self, page_num, blocks, used_indices):
        """Processes the main text stream, identifying formulas and headers."""
        acc = []
        for idx, block in enumerate(blocks):
            if idx in used_indices: continue
            content = block.get("block_content", "").strip()
            label = block.get("block_label", "").lower()
            
            temp_meta = self.meta_extractor.process_content_and_get_meta(content)
            if temp_meta.get("force_new_chunk") and acc:
                self._flush(acc, page_num)
                acc = []
            
            # Fixed: Validated formula existence in map before chunking
            f_match = re.search(r"\((\d+\.\d+)\)", content)
            formula_key = f_match.group(0) if f_match else None
            if formula_key and formula_key in self.formula_map:
                if acc: 
                    self._flush(acc, page_num)
                    acc = []
                self._add_formula_chunk(f_match.group(1), page_num)
                continue
            
            if label in ["header", "title"] and acc:
                self._flush(acc, page_num)
                acc = []
            
            if content and label not in ["footer", "number"]:
                acc.append(content)
        if acc: 
            self._flush(acc, page_num)

    def _handle_tables(self, page_num):
        """Converts extracted table metadata into document chunks."""
        if page_num in self.table_map:
            for tbl in self.table_map[page_num]:
                caption = re.sub('<[^<]+?>', '', tbl.get("caption_content", ""))
                meta_res = self.meta_extractor.process_content_and_get_meta(tbl.get("table_content", ""))
                chunk = self._create_chunk_obj("numbered_table", meta_res["clean_content"], page_num, meta_res)
                chunk.update({"entity_id": self._extract_id(caption), "caption": caption})
                self.final_chunks.append(chunk)

    def _create_chunk_obj(self, c_type, content, page, meta):
        """Helper to build a standardized chunk dictionary."""
        final_type = "exercise" if meta.get("is_exercise") or c_type == "exercise" else c_type
        return {
            "chunk_id": self._generate_deterministic_id(final_type, meta.get("subsubsection_number"), content),
            "entity_id": meta.get("subsubsection_number") or self._extract_id(content),
            "part": meta.get("part"),
            "section_title": meta.get("section_title"),
            "section_number": meta.get("section_number"),
            "subsection_title": meta.get("subsection_title"),
            "subsection_number": meta.get("subsection_number"),
            "subsubsection_title": meta.get("subsubsection_title"),
            "subsubsection_number": meta.get("subsubsection_number"),
            "chunk_type": final_type,
            "content": content, 
            "page": page,
            "image_links": []
        }

    def _is_inside(self, b1, b2):
        """Checks if bbox b1 is spatially contained within b2 with padding."""
        if not b1 or not b2 or len(b1) < 4 or len(b2) < 4: 
            return False
        return b1[0] >= b2[0]-BBOX_PADDING and b1[1] >= b2[1]-BBOX_PADDING and \
               b1[2] <= b2[2]+BBOX_PADDING and b1[3] <= b2[3]+BBOX_PADDING

    def _flush(self, acc, page):
        """Saves accumulated text lines as a single chunk."""
        raw_text = "\n".join(acc)
        meta_res = self.meta_extractor.process_content_and_get_meta(raw_text)
        if not meta_res.get("clean_content"): return
        chunk = self._create_chunk_obj("text", meta_res["clean_content"], page, meta_res)
        if hasattr(self.meta_extractor, 'get_references'):
            chunk.update(self.meta_extractor.get_references(meta_res["clean_content"]))
        self.final_chunks.append(chunk)

    def _extract_id(self, text):
        """Extracts numerical ID (e.g., 1.2) from a caption string."""
        if not text: return None
        m = re.search(r"(?:Exercise|Figure|Table|Algorithm|Example)?\s*(\d+\.\d+)", str(text), re.I)
        return m.group(1) if m else None

    def _save(self):
        """Persists all chunks to a final JSON file."""
        output = "ULTIMATE_BOOK_DATA.json"
        with open(output, "w", encoding="utf-8") as f:
            json.dump(self.final_chunks, f, indent=2, ensure_ascii=False)
        logger.info("assembly_success", total_chunks=len(self.final_chunks))

    def _generate_deterministic_id(self, chunk_type, entity_id, content):
        """Generates a stable unique ID for the chunk."""
        content_hash = hashlib.md5(content.encode('utf-8')).hexdigest()[:8]
        prefix = f"{chunk_type}_{entity_id}" if entity_id else chunk_type
        return f"{prefix}_{content_hash}"

if __name__ == "__main__":
    from config import PADDLE_RESULTS_DIR, OUTPUT_FIGURES_JSON, OUTPUT_BLOCKS_JSON, TABLES_JSON, FORMULAS_JSON
    
    assembler = DocumentAssembler(
        paddle_dir=PADDLE_RESULTS_DIR, 
        figures_json=OUTPUT_FIGURES_JSON,
        blocks_json=OUTPUT_BLOCKS_JSON,
        tables_json=TABLES_JSON,
        formulas_json=FORMULAS_JSON
    )
    assembler.assemble()