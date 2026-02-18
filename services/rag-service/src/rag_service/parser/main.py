import json
import os
import re
from metadata_extractor import MetadataExtractor

PAGE_OFFSET = 18 

class DocumentAssembler:
    def __init__(self, paddle_dir, figures_json, blocks_json, tables_json, formulas_json):
        print("[*] Assembler Initialization: Connecting Modules and Loading JSON...")
        
        self.paddle_pages = self._load_all_paddle_jsons(paddle_dir)
        
        self.image_map = self._load_and_offset(figures_json, "page")
        self.block_map = self._load_and_offset(blocks_json, "page")
        self.table_map = self._load_and_offset(tables_json, "page_number")
        
        with open(formulas_json, 'r', encoding='utf-8') as f:
            self.formula_map = json.load(f)

        self.meta_extractor = MetadataExtractor()
        
        self.final_chunks = []
        self.chunk_counter = 0

    def _load_and_offset(self, path, page_key):
        """Loads JSON and adjusts page numbers."""
        if not os.path.exists(path):
            print(f"[!] File not found: {path}")
            return {}
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            m = {}
            for item in data:
                actual_page = int(item[page_key]) + PAGE_OFFSET
                if actual_page not in m: m[actual_page] = []
                m[actual_page].append(item)
            return m

    def _load_all_paddle_jsons(self, directory):
        """Reads all PaddleOCR results and sorts them by page order."""
        combined = []
        if not os.path.exists(directory): return []
        files = sorted([f for f in os.listdir(directory) if f.endswith('.json')],
                       key=lambda f: [int(s) if s.isdigit() else s.lower() for s in re.split(r'(\d+)', f)])
        for file_name in files:
            with open(os.path.join(directory, file_name), 'r', encoding='utf-8') as f:
                data = json.load(f)
                combined.extend(data if isinstance(data, list) else [data])
        return combined

    def assemble(self):
        print(f"[*] Starting assembly of {len(self.paddle_pages)} pages...")

        for page_idx, page_data in enumerate(self.paddle_pages):
            page_num = int(page_data.get("page_num") or (page_idx + 1))
            blocks = page_data.get("prunedResult", {}).get("parsing_res_list", [])
            if not blocks: continue

            used_indices = set()
            visual_items = self.block_map.get(page_num, []) + self.image_map.get(page_num, [])
            
            merged_visuals = {}
            for item in visual_items:
                eid = item.get("entity_id") or self._extract_id(item.get("caption", ""))
                if eid not in merged_visuals:
                    merged_visuals[eid] = item
                else:
                    if "image_index" in item: merged_visuals[eid]["image_index"] = item["image_index"]
                    if "bbox" in item:
                        b1, b2 = merged_visuals[eid]["bbox"], item["bbox"]
                        merged_visuals[eid]["bbox"] = [
                            min(b1[0], b2[0]), min(b1[1], b2[1]), 
                            max(b1[2], b2[2]), max(b1[3], b2[3])
                        ]

            for eid, v_obj in merged_visuals.items():
                internal_text = []
                for idx, block in enumerate(blocks):
                    bbox = block.get("block_bbox")
                    if bbox and self._is_inside(bbox, v_obj["bbox"]):
                        internal_text.append(block["block_content"])
                        used_indices.add(idx)

                meta_res = self.meta_extractor.process_content_and_get_meta("\n".join(internal_text))
                chunk = self._create_chunk_obj(v_obj["chunk_type"], meta_res["clean_content"], page_num, meta_res)
                chunk["entity_id"] = eid
                chunk["caption"] = v_obj.get("caption", v_obj.get("content", ""))
                
                if "image_index" in v_obj:
                    chunk["image_links"] = [f"images/fig_{v_obj['image_index']}.png"]
                
                self.final_chunks.append(chunk)

            if page_num in self.table_map:
                for tbl in self.table_map[page_num]:
                    caption = re.sub('<[^<]+?>', '', tbl["caption_content"])
                    meta_res = self.meta_extractor.process_content_and_get_meta(tbl["table_content"])
                    chunk = self._create_chunk_obj("numbered_table", meta_res["clean_content"], page_num, meta_res)
                    chunk["entity_id"] = self._extract_id(caption)
                    chunk["caption"] = caption
                    self.final_chunks.append(chunk)

            acc = []
            for idx, block in enumerate(blocks):
                if idx in used_indices: continue
                content = block.get("block_content", "").strip()
                label = block.get("block_label", "").lower()
                
                temp_meta = self.meta_extractor.process_content_and_get_meta(content)
                if temp_meta["force_new_chunk"] and acc:
                    self._flush(acc, page_num)
                    acc = []

                f_match = re.search(r"\((\d+\.\d+)\)", content)
                if f_match and f_match.group(0) in self.formula_map:
                    if acc: self._flush(acc, page_num); acc = []
                    f_id = f_match.group(1)
                    meta_now = self.meta_extractor.process_content_and_get_meta("")
                    f_chunk = self._create_chunk_obj("numbered_formula", self.formula_map[f"({f_id})"], page_num, meta_now)
                    f_chunk["link_id"] = f_id
                    self.final_chunks.append(f_chunk)
                    continue

                if label in ["header", "title"] and acc:
                    self._flush(acc, page_num); acc = []
                
                if content and label not in ["footer", "number"]:
                    acc.append(content)

            if acc: self._flush(acc, page_num)

        self._save()

    def _flush(self, acc, page):
        """Converts accumulated text into chunks with cleaning and metadata."""
        raw_text = "\n".join(acc)
        meta_res = self.meta_extractor.process_content_and_get_meta(raw_text)
        if not meta_res["clean_content"]: return
        
        chunk = self._create_chunk_obj("text", meta_res["clean_content"], page, meta_res)
        
        refs = self.meta_extractor.get_references(meta_res["clean_content"])
        chunk.update(refs)
        self.final_chunks.append(chunk)

    def _create_chunk_obj(self, c_type, content, page, meta):
        """Chunk object constructor."""
        self.chunk_counter += 1
        
        final_type = c_type
        if meta.get("is_exercise") and c_type == "text":
            final_type = "exercise"

        return {
            "chunk_id": f"chunk_{self.chunk_counter:04d}",
            "entity_id": self._extract_id(content),
            "chapter_title": meta["chapter_title"],
            "section_title": meta["section_title"],
            "subsection_title": meta["subsection_title"],
            "chunk_type": final_type,
            "content": content,
            "page": page,
            "image_links": []
        }

    def _is_inside(self, b1, b2):
        return b1[0] >= b2[0]-35 and b1[1] >= b2[1]-35 and b1[2] <= b2[2]+35 and b1[3] <= b2[3]+35

    def _extract_id(self, text):
        """Reliable extraction of type 21.3 ID from the beginning of the text"""
        m = re.search(r"^(?:Exercise|Figure|Table|Algorithm|Example)?\s*(\d+\.\d+)", text.strip(), re.I)
        if not m:
            m = re.search(r"(?:Exercise|Figure|Table|Algorithm|Example)\s*(\d+\.\d+)", text[:100], re.I)
        return m.group(1) if m else None

    def _save(self):
        output = "ULTIMATE_BOOK_DATA.json"
        with open(output, "w", encoding="utf-8") as f:
            json.dump(self.final_chunks, f, indent=2, ensure_ascii=False)
        print(f"\n[SUCCESS] Save {len(self.final_chunks)} logical chunks.")

if __name__ == "__main__":
    base = "data_source"
    assembler = DocumentAssembler(
        paddle_dir=os.path.join(base, "paddle_results"), 
        figures_json=os.path.join(base, "figures_metadata.json"),
        blocks_json=os.path.join(base, "blocks_metadata.json"),
        tables_json=os.path.join(base, "extracted_tables.json"),
        formulas_json=os.path.join(base, "formula_mapping.json")
    )
    assembler.assemble()