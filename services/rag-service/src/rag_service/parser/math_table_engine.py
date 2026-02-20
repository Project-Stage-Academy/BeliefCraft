import math
import re
import json

class MathTableEngine:
    def __init__(self, side_notes_threshold=600):
        self.SIDE_NOTES_START_X = side_notes_threshold
        self.valid_num_pattern = re.compile(r'^\([A-Z0-9]+\.\d+\)$')
        self.table_caption_pattern = re.compile(r"(^|>)(table [\dA-Z]+\.\d+)", re.IGNORECASE)
        self.entity_id_pattern = re.compile(r"(\d+|[A-G])\.\d+")

    def _get_poly_bbox(self, item):
        """Extracts [min_x, min_y, max_x, max_y] from polygon or bbox  points."""
        if "block_polygon_points" in item and item["block_polygon_points"]:
            pts = item["block_polygon_points"]
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            return [min(xs), min(ys), max(xs), max(ys)]
        return item.get("block_bbox", [0, 0, 0, 0])

    def _has_horizontal_overlap(self, item_a, item_b):
        ax1, _, ax2, _ = self._get_poly_bbox(item_a)
        bx1, _, bx2, _ = self._get_poly_bbox(item_b)
        return max(ax1, bx1) < min(ax2, bx2)

    def _join_latex_parts(self, parts):
        if not parts: return ""
        if len(parts) == 1: return parts[0]
        return "\\begin{gathered}\n" + " \\\\ \n".join(parts) + "\n\\end{gathered}"

    def process_formulas(self, page_items):
        """Logic for processing formulas."""
        results = []
        claimed_ids = set()
        
        items = sorted(page_items, key=lambda x: self._get_poly_bbox(x)[1])
        numbers = [it for it in items if it["block_label"] == "formula_number" and self.valid_num_pattern.match(it["block_content"].strip())]
        formulas = [it for it in items if it["block_label"] == "display_formula"]

        for num in numbers:
            num_str = num["block_content"].strip()
            nbb = self._get_poly_bbox(num)
            candidates = []

            for f in formulas:
                if id(f) in claimed_ids: continue
                fbb = self._get_poly_bbox(f)
                v_overlap = max(fbb[1], nbb[1]) < min(fbb[3], nbb[3])
                if v_overlap and fbb[2] <= nbb[2]:
                    candidates.append(f)

            if not candidates:
                best_dist = float('inf')
                best_f = None
                for f in formulas:
                    if id(f) in claimed_ids: continue
                    fbb = self._get_poly_bbox(f)
                    if fbb[3] <= nbb[3] + 20:
                        dist = math.hypot(nbb[0] - fbb[2], nbb[1] - fbb[1])
                        if dist < 600 and dist < best_dist:
                            best_dist = dist
                            best_f = f
                if best_f: candidates.append(best_f)

            if candidates:
                if len(candidates) == 1:
                    main_f = candidates[0]
                    claimed_ids.add(id(main_f))
                    extras = []
                    curr = main_f
                    idx = items.index(main_f)
                    for i in range(idx - 1, -1, -1):
                        prev = items[i]
                        if prev["block_label"] == "display_formula" and id(prev) not in claimed_ids:
                            if self._has_horizontal_overlap(prev, curr):
                                extras.insert(0, prev["block_content"])
                                claimed_ids.add(id(prev))
                                curr = prev
                            else: break
                        else: break
                    
                    full_latex = self._join_latex_parts(extras + [main_f["block_content"]])
                    entity_id = num_str.strip("()")
                    results.append({
                        "chunk_type": "numbered_formula",
                        "entity_id": entity_id,
                        "content": full_latex,
                        "bbox": nbb
                    })
        return results

    def process_tables(self, page_items, page_num):
        """Logic for processing tables."""
        results = []
        tables = []
        captions = []

        for it in page_items:
            bbox = self._get_poly_bbox(it)
            if it["block_label"] == "table":
                tables.append({"item": it, "bbox": bbox, "center": ((bbox[0]+bbox[2])/2, (bbox[1]+bbox[3])/2)})
            elif bbox[0] > self.SIDE_NOTES_START_X:
                content = it.get("block_content", "").strip()
                if self.table_caption_pattern.search(content):
                    captions.append({"item": it, "bbox": bbox, "center": ((bbox[0]+bbox[2])/2, (bbox[1]+bbox[3])/2), "content": content})

        for cap in captions:
            best_table = None
            min_dist = float('inf')
            for tab in tables:
                dist = math.hypot(cap["center"][0] - tab["center"][0], cap["center"][1] - tab["center"][1])
                if dist < min_dist:
                    min_dist = dist
                    best_table = tab
            
            if best_table:
                entity_match = self.entity_id_pattern.search(cap["content"])
                results.append({
                    "chunk_type": "numbered_table",
                    "entity_id": entity_match.group(0) if entity_match else None,
                    "content": best_table["item"]["block_content"],
                    "caption": cap["content"],
                    "bbox": best_table["bbox"]
                })
        return results

# Test
if __name__ == "__main__":
    mock_items = [
        {"block_label": "display_formula", "block_content": "E = mc^2", "block_bbox": [100, 100, 200, 120]},
        {"block_label": "formula_number", "block_content": "(1.1)", "block_bbox": [500, 100, 550, 120]},
        {"block_label": "table", "block_content": "| A | B |\n|---|---|\n| 1 | 2 |", "block_bbox": [100, 300, 400, 400]},
        {"block_label": "text", "block_content": "Table 1.1: Stats", "block_bbox": [610, 310, 750, 330]} 
    ]
    
    engine = MathTableEngine()
    formulas = engine.process_formulas(mock_items)
    tables = engine.process_tables(mock_items, 1)
    
    print("--- Formulas Found ---")
    print(json.dumps(formulas, indent=2))
    print("\n--- Tables Found ---")
    print(json.dumps(tables, indent=2))