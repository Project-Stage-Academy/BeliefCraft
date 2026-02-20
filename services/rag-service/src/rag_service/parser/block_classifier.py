import fitz
import re
import json
from enum import Enum
from tqdm import tqdm

COLUMNS_DIVIDER_X = 300  
DISTANCE_BETWEEN_NOTES = 20  
DISTANCE_OFFSET_X = 100  
GRAY_FILL_THRESHOLD = 0.9 

class BlockType(Enum):
    ALGORITHM = "algorythm" 
    EXAMPLE = "example"
    OTHER = "other"

class BlockProcessor:
    def __init__(self, pdf_path):
        self.doc = fitz.open(pdf_path)
        self.algorithms_pattern = re.compile(r"^Algorithm\s+(?:\d+|[A-G])\.\d+", re.IGNORECASE)
        self.example_pattern = re.compile(r"^Example\s+(?:\d+|[A-G])\.\d+", re.IGNORECASE)

    def _determine_block_type(self, text):
        clean_text = text.strip()
        if self.algorithms_pattern.match(clean_text): return BlockType.ALGORITHM.value
        if self.example_pattern.match(clean_text): return BlockType.EXAMPLE.value
        return BlockType.OTHER.value

    def _extract_captions(self, page):
        page_dict = page.get_text("dict")
        captions = []
        for block in page_dict.get("blocks", []):
            if "lines" not in block: continue
            first_line_text = "".join([span["text"] for span in block["lines"][0]["spans"]])
            b_type = self._determine_block_type(first_line_text)
            
            if b_type != BlockType.OTHER.value:
                caption_text = ""
                caption_rect = None
                prev_y1 = None
                for line in block["lines"]:
                    if line["bbox"][0] > COLUMNS_DIVIDER_X:
                        if prev_y1 and line["bbox"][1] - prev_y1 > DISTANCE_BETWEEN_NOTES: break
                        line_rect = fitz.Rect(line["bbox"])
                        caption_rect = line_rect if caption_rect is None else caption_rect | line_rect
                        caption_text += " ".join([s["text"] for s in line["spans"]]) + " "
                        prev_y1 = line["bbox"][3]
                if caption_text:
                    captions.append({"text": caption_text.strip(), "bbox": caption_rect, "type": b_type})
        return captions

    def run(self, output_path="blocks_metadata.json"):
        all_blocks = []
        for page_num in tqdm(range(len(self.doc)), desc="Витягування сірих блоків"):
            page = self.doc.load_page(page_num)
            drawings = page.get_drawings()
            captions = self._extract_captions(page)
            
            for cap in captions:
                test_point = fitz.Point(cap["bbox"].x0 - DISTANCE_OFFSET_X, cap["bbox"].y0 + 5)
                
                for draw in drawings:
                    if draw["fill"] and draw["fill"][0] > GRAY_FILL_THRESHOLD:
                        if draw["rect"].contains(test_point):
                            block_rect = draw["rect"]
                            raw_content = page.get_text("text", clip=block_rect).strip()
                            
                            entity_id = (re.search(r"(\d+\.\d+)", cap["text"]) or [None])[0]
                            
                            all_blocks.append({
                                "chunk_type": cap["type"],
                                "entity_id": entity_id,
                                "content": raw_content, 
                                "caption": cap["text"],
                                "page": page_num + 1,
                                "bbox": [block_rect.x0, block_rect.y0, block_rect.x1, block_rect.y1]
                            })
                            break
        
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(all_blocks, f, indent=2, ensure_ascii=False)
        self.doc.close()

if __name__ == "__main__":
    processor = BlockProcessor("dm.pdf")
    processor.run()