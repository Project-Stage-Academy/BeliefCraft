"""
Characterization tests for MathTableEngine and the module-level
clean_html_attributes() helper.

These tests lock the *current* spatial-matching and HTML-cleaning behaviour
so that future refactors cannot silently break it.
"""

import pytest
from pipeline.parsing.math_table_engine import MathTableEngine, clean_html_attributes

# Hardcoded to lock the current module-level defaults at the time of writing.
# If these values change in production code the tests will correctly fail.
_SIDE_NOTES_THRESHOLD_X = 600
_MAX_FORMULA_DISTANCE = 600
_VERTICAL_TOLERANCE = 5


@pytest.fixture()
def engine() -> MathTableEngine:
    return MathTableEngine(side_notes_threshold=_SIDE_NOTES_THRESHOLD_X)


# ---------------------------------------------------------------------------
# _get_poly_bbox effect on process_formulas()
# ---------------------------------------------------------------------------


def test_formula_matched_using_polygon_points_when_present(engine: MathTableEngine) -> None:
    """Locks: when block_polygon_points is present it is used for vertical overlap
    matching; block_bbox is ignored.  The formula and number both have polygon Y=100-120
    but their block_bbox Y values are far apart (>MAX_FORMULA_DISTANCE), so a match is
    only possible if polygon_points are used.
    """
    formula_item = {
        "block_label": "display_formula",
        "block_content": "E = mc^2",
        # polygon Y=100-120; block_bbox Y=50-100 (far from number)
        "block_polygon_points": [[50, 100], [300, 100], [300, 120], [50, 120]],
        "block_bbox": [50, 50, 300, 100],
    }
    num_item = {
        "block_label": "formula_number",
        "block_content": "(1.1)",
        # polygon Y=100-120; block_bbox Y=800-820 (distance > MAX_FORMULA_DISTANCE)
        "block_polygon_points": [[400, 100], [460, 100], [460, 120], [400, 120]],
        "block_bbox": [400, 800, 460, 820],
    }

    results = engine.process_formulas([formula_item, num_item])

    assert len(results) == 1
    assert results[0]["entity_id"] == "1.1"


def test_formula_matched_using_block_bbox_when_no_polygon_points(
    engine: MathTableEngine,
) -> None:
    """Locks: when block_polygon_points is absent, block_bbox is used as the fallback
    geometry source for vertical overlap detection.
    """
    formula_item = {
        "block_label": "display_formula",
        "block_content": "a^2 + b^2 = c^2",
        "block_bbox": [50, 100, 300, 120],
    }
    num_item = {
        "block_label": "formula_number",
        "block_content": "(2.3)",
        "block_bbox": [400, 100, 460, 120],
    }

    results = engine.process_formulas([formula_item, num_item])

    assert len(results) == 1
    assert results[0]["entity_id"] == "2.3"


# ---------------------------------------------------------------------------
# clean_html_attributes (module-level)
# ---------------------------------------------------------------------------


def test_clean_html_attributes_keeps_colspan_and_rowspan_on_table_tags() -> None:
    """Locks: colspan and rowspan survive on <table>, <tr>, <td>, <th> tags;
    all other attributes are removed.
    """
    html = (
        '<table style="color:red" border="1">'
        '<tr id="row1"><td colspan="3" rowspan="2" class="x">cell</td></tr>'
        "</table>"
    )

    result = clean_html_attributes(html)

    assert 'colspan="3"' in result
    assert 'rowspan="2"' in result
    assert "style=" not in result
    assert "border=" not in result
    assert 'id="row1"' not in result
    assert "class=" not in result


def test_clean_html_attributes_keeps_href_on_anchor_removes_class() -> None:
    """Locks: href is preserved on <a> tags; all other attributes (class, id, …) are removed."""
    html = '<a href="https://example.com" class="btn" id="link1">click</a>'

    result = clean_html_attributes(html)

    assert 'href="https://example.com"' in result
    assert "class=" not in result
    assert 'id="link1"' not in result


def test_clean_html_attributes_removes_all_attrs_from_non_table_non_anchor_tags() -> None:
    """Locks: for tags other than table-family and <a>, ALL attributes are stripped."""
    html = '<p class="para" id="p1">text</p><span style="color:blue">span</span>'

    result = clean_html_attributes(html)

    assert "class=" not in result
    assert 'id="p1"' not in result
    assert "style=" not in result
    assert "text" in result
    assert "span" in result


def test_clean_html_attributes_passthrough_for_empty_string() -> None:
    """Locks: empty string input is returned unchanged (no crash, no mutation)."""
    assert clean_html_attributes("") == ""


def test_clean_html_attributes_passthrough_for_whitespace_only() -> None:
    """Locks: whitespace-only input is returned as-is (truthy html.strip() is empty)."""
    result = clean_html_attributes("   ")
    assert result == "   "


# ---------------------------------------------------------------------------
# process_formulas — vertical overlap linking
# ---------------------------------------------------------------------------


def _make_formula_item(content: str, bbox: list[float]) -> dict:
    return {"block_label": "display_formula", "block_content": content, "block_bbox": bbox}


def _make_num_item(content: str, bbox: list[float]) -> dict:
    return {"block_label": "formula_number", "block_content": content, "block_bbox": bbox}


def test_process_formulas_links_by_vertical_overlap(engine: MathTableEngine) -> None:
    """Locks: a formula_number block that vertically overlaps a display_formula
    (with VERTICAL_TOLERANCE) is linked to it.
    """
    page_items = [
        _make_formula_item("E = mc^2", [50, 100, 300, 120]),
        # same Y band, to the right of the formula
        _make_num_item("(1.1)", [400, 100, 460, 120]),
    ]

    results = engine.process_formulas(page_items)

    assert len(results) == 1
    assert results[0]["entity_id"] == "1.1"
    assert "E = mc^2" in results[0]["content"]
    assert results[0]["chunk_type"] == "numbered_formula"


def test_process_formulas_fallback_by_nearest_distance_when_no_vertical_overlap(
    engine: MathTableEngine,
) -> None:
    """Locks: when no vertical overlap exists, the nearest unclaimed formula within
    MAX_FORMULA_DISTANCE is used as a fallback.
    """
    page_items = [
        # formula is above the number (no Y overlap)
        _make_formula_item("x^2 + y^2", [50, 50, 300, 70]),
        # number is below, within FORMULA_Y_OFFSET_BUFFER distance
        _make_num_item("(2.3)", [400, 75, 460, 90]),
    ]

    results = engine.process_formulas(page_items)

    assert len(results) == 1
    assert results[0]["entity_id"] == "2.3"
    assert "x^2 + y^2" in results[0]["content"]


def test_process_formulas_invalid_number_format_ignored(engine: MathTableEngine) -> None:
    """Locks: formula_number blocks whose content does not match r'^\\([A-Z0-9]+\\.\\d+\\)$'
    are silently ignored and produce no output.
    """
    page_items = [
        _make_formula_item("F = ma", [50, 100, 300, 120]),
        # invalid: no parentheses, lowercase
        _make_num_item("1.1", [400, 100, 460, 120]),
        # invalid: missing dot-number suffix
        _make_num_item("(ABC)", [400, 130, 460, 150]),
    ]

    results = engine.process_formulas(page_items)

    assert results == []


def test_process_formulas_valid_number_pattern_uppercase_alphanumeric(
    engine: MathTableEngine,
) -> None:
    """Locks: formula number like (A.3) with uppercase letter prefix is accepted."""
    page_items = [
        _make_formula_item("\\alpha + \\beta", [50, 100, 300, 120]),
        _make_num_item("(A.3)", [400, 100, 460, 120]),
    ]

    results = engine.process_formulas(page_items)

    assert len(results) == 1
    assert results[0]["entity_id"] == "A.3"


def test_process_formulas_multi_line_grouping_uses_gathered(engine: MathTableEngine) -> None:
    """Locks: multiple horizontally-overlapping formula blocks above the matched formula
    are combined using \\begin{gathered}...\\end{gathered}.
    """
    page_items = [
        # top formula line
        _make_formula_item("a = b", [50, 80, 300, 95]),
        # bottom formula line (main match)
        _make_formula_item("c = d", [50, 100, 300, 115]),
        # number aligned with the bottom line
        _make_num_item("(3.1)", [400, 100, 460, 115]),
    ]

    results = engine.process_formulas(page_items)

    assert len(results) == 1
    content = results[0]["content"]
    assert "\\begin{gathered}" in content
    assert "a = b" in content
    assert "c = d" in content


# ---------------------------------------------------------------------------
# process_tables — caption detection and spatial matching
# ---------------------------------------------------------------------------


def _make_table_item(content: str, bbox: list[float]) -> dict:
    return {"block_label": "table", "block_content": content, "block_bbox": bbox}


def _make_side_note(content: str, x_start: float = 650.0, y: float = 200.0) -> dict:
    # x_start > _SIDE_NOTES_THRESHOLD_X (600) — in the side-note region
    return {
        "block_label": "text",
        "block_content": content,
        "block_bbox": [x_start, y, x_start + 150, y + 30],
    }


def test_process_tables_detects_caption_in_side_note_region(engine: MathTableEngine) -> None:
    """Locks: a text block with X > SIDE_NOTES_THRESHOLD_X whose content matches
    'Table N.M' is identified as a caption and associated with the nearest table.
    """
    page_items = [
        _make_table_item("<table><tr><td>Data</td></tr></table>", [100, 190, 400, 420]),
        _make_side_note("Table 2.1. Summary of results"),
    ]

    results = engine.process_tables(page_items, page_num=1)

    assert len(results) == 1
    assert results[0]["chunk_type"] == "numbered_table"
    assert results[0]["entity_id"] == "2.1"
    assert results[0]["caption"] == "Table 2.1. Summary of results"


def test_process_tables_nearest_table_wins_spatial_matching(engine: MathTableEngine) -> None:
    """Locks: when multiple tables are present, the nearest one (by Euclidean centre
    distance) is matched to the caption.
    """
    page_items = [
        # near table — centre ~(250, 100)
        _make_table_item("<table><tr><td>Near</td></tr></table>", [100, 50, 400, 150]),
        # far table — centre ~(250, 600)
        _make_table_item("<table><tr><td>Far</td></tr></table>", [100, 550, 400, 650]),
        # caption Y=100, should match near table
        _make_side_note("Table 5.5. Near results", x_start=650.0, y=100.0),
    ]

    results = engine.process_tables(page_items, page_num=1)

    assert len(results) == 1
    assert "Near" in results[0]["content"]


def test_process_tables_caption_below_threshold_x_is_not_detected(
    engine: MathTableEngine,
) -> None:
    """Locks: text blocks with X <= SIDE_NOTES_THRESHOLD_X are NOT treated as table captions."""
    page_items = [
        _make_table_item("<table><tr><td>Data</td></tr></table>", [100, 190, 400, 420]),
        # X=300 is below threshold (600)
        {
            "block_label": "text",
            "block_content": "Table 1.1. In main body",
            "block_bbox": [300, 200, 500, 220],
        },
    ]

    results = engine.process_tables(page_items, page_num=1)

    assert results == []


def test_process_tables_no_table_blocks_returns_empty_list(engine: MathTableEngine) -> None:
    """Locks: if there are no 'table'-labelled blocks, process_tables returns []."""
    page_items = [_make_side_note("Table 1.1. Caption only")]

    results = engine.process_tables(page_items, page_num=1)

    assert results == []


def test_process_tables_entity_id_extracted_from_caption_content(
    engine: MathTableEngine,
) -> None:
    """Locks: entity_id on the result matches the X.Y number inside the caption string."""
    page_items = [
        _make_table_item("<table/>", [100, 100, 400, 300]),
        _make_side_note("Table 7.12 Details"),
    ]

    results = engine.process_tables(page_items, page_num=1)

    assert results[0]["entity_id"] == "7.12"
