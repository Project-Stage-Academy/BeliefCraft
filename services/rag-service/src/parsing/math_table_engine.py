import math
import re
import json
import logging
from common.logging import get_logger

# Module-level constants for geometric analysis
SIDE_NOTES_THRESHOLD_X = 600
MAX_FORMULA_DISTANCE = 600
FORMULA_Y_OFFSET_BUFFER = 20
VERTICAL_TOLERANCE = 5  # Added tolerance for better overlap detection

logger = get_logger(__name__)

class MathTableEngine:
    """
    Engine for associating mathematical formulas and tables with their 
    respective numbers and captions based on spatial layout.
    """
    def __init__(self, side_notes_threshold=SIDE_NOTES_THRESHOLD_X):
        self.SIDE_NOTES_START_X = side_notes_threshold
        self.valid_num_pattern = re.compile(r'^\([A-Z0-9]+\.\d+\)$')
        self.table_caption_pattern = re.compile(r"(^|>)(table [\dA-Z]+\.\d+)", re.IGNORECASE)
        self.entity_id_pattern = re.compile(r"(\d+|[A-G])\.\d+")

    def _get_poly_bbox(self, item):
        """
        Calculates a bounding box [min_x, min_y, max_x, max_y] from 
        polygon points or a standard bbox.
        """
        if "block_polygon_points" in item and item["block_polygon_points"]:
            pts = item["block_polygon_points"]
            return [min(p[0] for p in pts), min(p[1] for p in pts), 
                    max(p[0] for p in pts), max(p[1] for p in pts)]
        return item.get("block_bbox", [0, 0, 0, 0])

    def _has_horizontal_overlap(self, item_a, item_b):
        """Checks if two items overlap horizontally."""
        ax1, _, ax2, _ = self._get_poly_bbox(item_a)
        bx1, _, bx2, _ = self._get_poly_bbox(item_b)
        return max(ax1, bx1) < min(ax2, bx2)

    def _join_latex_parts(self, parts):
        """Combines multiple LaTeX formula parts into a gathered environment."""
        if not parts: return ""
        if len(parts) == 1: return parts[0]
        return "\\begin{gathered}\n" + " \\\\ \n".join(parts) + "\n\\end{gathered}"

    def process_formulas(self, page_items):
        """
        Links detected formula numbers (e.g., (1.1)) to their LaTeX content 
        by analyzing vertical alignment and distance.
        """
        results = []
        claimed_ids = set()
        
        # Sort items by Y coordinate to process from top to bottom
        sorted_items = sorted(page_items, key=lambda x: self._get_poly_bbox(x)[1])
        
        numbers = [it for it in sorted_items if it["block_label"] == "formula_number" 
                   and self.valid_num_pattern.match(it.get("block_content", "").strip())]
        formulas = [it for it in sorted_items if it["block_label"] == "display_formula"]

        for num in numbers:
            num_str = num["block_content"].strip()
            nbb = self._get_poly_bbox(num)
            candidates = []

            for f in formulas:
                if id(f) in claimed_ids: continue
                fbb = self._get_poly_bbox(f)
                
                # Fixed: Added VERTICAL_TOLERANCE to handle minor scanning/alignment issues
                v_overlap = max(fbb[1], nbb[1]) < min(fbb[3], nbb[3]) + VERTICAL_TOLERANCE
                if v_overlap and fbb[2] <= nbb[2]:
                    candidates.append(f)

            if not candidates:
                best_dist = float('inf')
                best_f = None
                for f in formulas:
                    if id(f) in claimed_ids: continue
                    fbb = self._get_poly_bbox(f)
                    if fbb[3] <= nbb[3] + FORMULA_Y_OFFSET_BUFFER:
                        dist = math.hypot(nbb[0] - fbb[2], nbb[1] - fbb[1])
                        if dist < MAX_FORMULA_DISTANCE and dist < best_dist:
                            best_dist, best_f = dist, f
                if best_f: candidates.append(best_f)

            if candidates:
                main_f = candidates[0]
                claimed_ids.add(id(main_f))
                extras = []
                
                curr = main_f
                try:
                    idx = sorted_items.index(main_f)
                    for i in range(idx - 1, -1, -1):
                        prev = sorted_items[i]
                        if prev["block_label"] == "display_formula" and id(prev) not in claimed_ids:
                            if self._has_horizontal_overlap(prev, curr):
                                extras.insert(0, prev["block_content"])
                                claimed_ids.add(id(prev))
                                curr = prev
                            else: break
                        else: break
                except ValueError: pass

                results.append({
                    "chunk_type": "numbered_formula",
                    "entity_id": num_str.strip("()"),
                    "content": self._join_latex_parts(extras + [main_f["block_content"]]),
                    "bbox": nbb
                })
        return results

    def process_tables(self, page_items, page_num):
        """
        Associates tables with their captions found in side notes using 
        nearest-neighbor spatial matching.
        """
        results = []
        tables = []
        captions = []

        for it in page_items:
            bbox = self._get_poly_bbox(it)
            if it.get("block_label") == "table":
                tables.append({
                    "item": it, "bbox": bbox, 
                    "center": ((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2)
                })
            elif bbox[0] > self.SIDE_NOTES_START_X:
                content = it.get("block_content", "").strip()
                if self.table_caption_pattern.search(content):
                    captions.append({
                        "item": it, "center": ((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2), 
                        "content": content
                    })

        for cap in captions:
            best_table = None
            min_dist = float('inf')
            for tab in tables:
                dist = math.hypot(cap["center"][0] - tab["center"][0], cap["center"][1] - tab["center"][1])
                if dist < min_dist:
                    min_dist, best_table = dist, tab
            
            if best_table:
                # Fixed: Removed walrus operator for better readability as requested
                entity_match = self.entity_id_pattern.search(cap["content"])
                entity_id = entity_match.group(0) if entity_match else None
                
                results.append({
                    "chunk_type": "numbered_table",
                    "entity_id": entity_id,
                    "content": best_table["item"]["block_content"],
                    "caption": cap["content"],
                    "bbox": best_table["bbox"]
                })
        return results