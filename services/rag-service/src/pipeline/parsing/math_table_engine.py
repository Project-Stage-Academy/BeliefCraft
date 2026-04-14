import math
import re
from typing import Any

from bs4 import BeautifulSoup
from common.logging import get_logger

# Module-level constants for geometric analysis
SIDE_NOTES_THRESHOLD_X = 600
MAX_FORMULA_DISTANCE = 600
FORMULA_Y_OFFSET_BUFFER = 20
VERTICAL_TOLERANCE = 5  # Added tolerance for better overlap detection

TABLE_TAGS = {"table", "tr", "td", "th"}
TABLE_ATTRS_TO_KEEP = {"colspan", "rowspan"}
LINK_ATTRS_TO_KEEP = {"href"}
FIELDS_TO_CLEAN = {"content", "caption"}

logger = get_logger(__name__)


def clean_html_attributes(html_text: str) -> str:
    """
    Removes all HTML attributes except:
    href for <a> and colspan, rowspan for table-related tags.
    """
    if not html_text or not html_text.strip():
        return html_text

    soup = BeautifulSoup(html_text, "html.parser")

    for tag in soup.find_all(True):
        if tag.name in TABLE_TAGS:
            tag.attrs = {k: v for k, v in tag.attrs.items() if k.lower() in TABLE_ATTRS_TO_KEEP}

        elif tag.name == "a":
            tag.attrs = {k: v for k, v in tag.attrs.items() if k.lower() in LINK_ATTRS_TO_KEEP}

        else:
            tag.attrs = {}

    return str(soup)


class MathTableEngine:
    """
    Engine for associating mathematical formulas and tables with their
    respective numbers and captions based on spatial layout.
    """

    def __init__(self, side_notes_threshold: int = SIDE_NOTES_THRESHOLD_X) -> None:
        self.SIDE_NOTES_START_X = side_notes_threshold
        self.valid_num_pattern = re.compile(r"^\([A-Z0-9]+\.\d+\)$")
        self.table_caption_pattern = re.compile(r"(^|>)(table [\dA-Z]+\.\d+)", re.IGNORECASE)
        self.entity_id_pattern = re.compile(r"(\d+|[A-G])\.\d+")

    def _get_poly_bbox(self, item: dict[str, Any]) -> list[float]:
        """
        Calculates a bounding box [min_x, min_y, max_x, max_y] from
        polygon points or a standard bbox.
        """
        if "block_polygon_points" in item and item["block_polygon_points"]:
            pts: list[list[float]] = item["block_polygon_points"]
            return [
                float(min(p[0] for p in pts)),
                float(min(p[1] for p in pts)),
                float(max(p[0] for p in pts)),
                float(max(p[1] for p in pts)),
            ]
        res = item.get("block_bbox", [0.0, 0.0, 0.0, 0.0])
        return [float(x) for x in res]

    def _has_horizontal_overlap(self, item_a: dict[str, Any], item_b: dict[str, Any]) -> bool:
        ax1, _, ax2, _ = self._get_poly_bbox(item_a)
        bx1, _, bx2, _ = self._get_poly_bbox(item_b)
        return max(ax1, bx1) < min(ax2, bx2)

    def _join_latex_parts(self, parts: list[str]) -> str:
        if not parts:
            return ""
        if len(parts) == 1:
            return parts[0]
        return "\\begin{gathered}\n" + " \\\\ \n".join(parts) + "\n\\end{gathered}"

    def process_formulas(self, page_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Links detected formula numbers (e.g., (1.1)) to their LaTeX content
        by analyzing vertical alignment and distance.
        """
        results: list[dict[str, Any]] = []
        claimed_ids: set[int] = set()

        # Sort items by Y coordinate to process from top to bottom
        sorted_items = sorted(page_items, key=lambda x: self._get_poly_bbox(x)[1])

        numbers = [
            it
            for it in sorted_items
            if it["block_label"] == "formula_number"
            and self.valid_num_pattern.match(it.get("block_content", "").strip())
        ]
        formulas = [it for it in sorted_items if it["block_label"] == "display_formula"]

        for num in numbers:
            num_str = num["block_content"].strip()
            nbb = self._get_poly_bbox(num)
            candidates: list[dict[str, Any]] = []

            for f in formulas:
                if id(f) in claimed_ids:
                    continue
                fbb = self._get_poly_bbox(f)
                v_overlap = max(fbb[1], nbb[1]) < min(fbb[3], nbb[3]) + VERTICAL_TOLERANCE
                if v_overlap and fbb[2] <= nbb[2]:
                    candidates.append(f)

            if not candidates:
                best_dist = float("inf")
                best_f = None
                for f in formulas:
                    if id(f) in claimed_ids:
                        continue
                    fbb = self._get_poly_bbox(f)
                    if fbb[3] <= nbb[3] + FORMULA_Y_OFFSET_BUFFER:
                        dist = math.hypot(nbb[0] - fbb[2], nbb[1] - fbb[1])
                        if dist < MAX_FORMULA_DISTANCE and dist < best_dist:
                            best_dist, best_f = dist, f
                if best_f:
                    candidates.append(best_f)

            if candidates:
                main_f = candidates[0]
                claimed_ids.add(id(main_f))
                extras: list[str] = []

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
                            else:
                                break
                        else:
                            break
                except ValueError:
                    pass

                chunk = {
                    "chunk_type": "numbered_formula",
                    "entity_id": num_str.strip("()"),
                    "content": self._join_latex_parts(extras + [main_f["block_content"]]),
                    "bbox": nbb,
                }

                results.append(self._clean_chunk_fields(chunk))

        return results

    def process_tables(
        self, page_items: list[dict[str, Any]], page_num: int
    ) -> list[dict[str, Any]]:
        """
        Associates tables with their captions found in side notes using
        nearest-neighbor spatial matching.
        """
        results: list[dict[str, Any]] = []
        tables: list[dict[str, Any]] = []
        captions: list[dict[str, Any]] = []

        for it in page_items:
            bbox = self._get_poly_bbox(it)
            if it.get("block_label") == "table":
                tables.append(
                    {
                        "item": it,
                        "bbox": bbox,
                        "center": ((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2),
                    }
                )
            elif bbox[0] > self.SIDE_NOTES_START_X:
                content = it.get("block_content", "").strip()
                if self.table_caption_pattern.search(content):
                    captions.append(
                        {
                            "item": it,
                            "center": (
                                float((bbox[0] + bbox[2]) / 2),
                                float((bbox[1] + bbox[3]) / 2),
                            ),
                            "content": content,
                        }
                    )

        for cap in captions:
            best_table = None
            min_dist = float("inf")
            cap_center = cap["center"]

            for tab in tables:
                tab_center = tab["center"]
                dist = math.hypot(cap_center[0] - tab_center[0], cap_center[1] - tab_center[1])
                if dist < min_dist:
                    min_dist, best_table = dist, tab

            if best_table:
                # Fixed: Removed walrus operator for better readability as requested
                entity_match = self.entity_id_pattern.search(cap["content"])
                entity_id = entity_match.group(0) if entity_match else None

                results.append(
                    {
                        "chunk_type": "numbered_table",
                        "entity_id": entity_id,
                        "content": best_table["item"]["block_content"],
                        "caption": cap["content"],
                        "bbox": best_table["bbox"],
                    }
                )
        return results

    def _clean_chunk_fields(self, chunk: dict[str, Any]) -> dict[str, Any]:
        "Cleans all HTML fields inside a single chunk."
        for field in FIELDS_TO_CLEAN:
            if field in chunk and isinstance(chunk[field], str):
                chunk[field] = clean_html_attributes(chunk[field])
        return chunk
