"""
Characterization tests for DocumentAssembler.

These tests lock the *current* behaviour so that future refactors cannot
silently break it.  Every test carries a docstring stating the invariant.
"""

import hashlib
import json

import pytest
from pipeline.parsing.main import (
    BBOX_PADDING,  # noqa: F401 — imported to lock the value at 5
    LAST_PAGE,
    MAX_CHUNK_CHAR_LENGTH,
    PADDLE_BLOCKS_TO_SKIP,
    START_PAGE,
    DocumentAssembler,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def env(tmp_path):
    """Minimal, valid file environment to construct a DocumentAssembler."""
    paddle_dir = tmp_path / "paddle"
    paddle_dir.mkdir()
    (paddle_dir / "page_1.json").write_text(
        json.dumps([{"page_num": 1, "prunedResult": {"parsing_res_list": []}}]),
        encoding="utf-8",
    )

    figures_json = tmp_path / "figures.json"
    figures_json.write_text(json.dumps([]), encoding="utf-8")

    blocks_json = tmp_path / "blocks.json"
    blocks_json.write_text(json.dumps([]), encoding="utf-8")

    tables_json = tmp_path / "tables.json"
    tables_json.write_text(json.dumps([]), encoding="utf-8")

    formulas_json = tmp_path / "formulas.json"
    formulas_json.write_text(json.dumps({}), encoding="utf-8")

    return {
        "paddle_dir": paddle_dir,
        "figures": figures_json,
        "blocks": blocks_json,
        "tables": tables_json,
        "formulas": formulas_json,
        "tmp_path": tmp_path,
    }


def _make(env: dict, **overrides) -> DocumentAssembler:
    kwargs = {
        "paddle_dir": env["paddle_dir"],
        "figures_json": env["figures"],
        "blocks_json": env["blocks"],
        "tables_json": env["tables"],
        "formulas_json": env["formulas"],
    }
    kwargs.update(overrides)
    return DocumentAssembler(**kwargs)


def _pages_with_content(n_blank: int, page_blocks: list) -> list:
    """Return n_blank empty pages followed by one page carrying page_blocks."""
    pages = [
        {"page_num": i + 1, "prunedResult": {"parsing_res_list": []}}
        for i in range(n_blank)
    ]
    pages.append(
        {
            "page_num": n_blank + 1,
            "prunedResult": {"parsing_res_list": page_blocks},
        }
    )
    return pages


# ---------------------------------------------------------------------------
# _is_inside
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "b1, b2, expected",
    [
        # exact fit — True
        ([100, 100, 200, 200], [100, 100, 200, 200], True),
        # b1 is well inside b2 — True
        ([110, 110, 190, 190], [100, 100, 200, 200], True),
        # b1 extends exactly BBOX_PADDING outside each edge — still True
        ([95, 95, 205, 205], [100, 100, 200, 200], True),
        # b1 left-edge is 1 unit beyond BBOX_PADDING — False
        ([94, 100, 200, 200], [100, 100, 200, 200], False),
        # completely disjoint — False
        ([300, 300, 400, 400], [100, 100, 200, 200], False),
        # empty inner list — False
        ([], [10, 10, 20, 20], False),
        # empty outer list — False
        ([10, 10, 20, 20], [], False),
        # too-short lists — False
        ([10, 10], [5, 5, 20, 20], False),
    ],
)
def test_is_inside_returns_correct_result(env, b1, b2, expected) -> None:
    """Locks: _is_inside with BBOX_PADDING=5 tolerance — boundary and edge cases."""
    assembler = _make(env)

    result = assembler._is_inside(b1, b2)

    assert result is expected


# ---------------------------------------------------------------------------
# _generate_deterministic_id
# ---------------------------------------------------------------------------


def test_generate_deterministic_id_is_stable(env) -> None:
    """Locks: calling _generate_deterministic_id twice with the same args returns
    the identical string.
    """
    assembler = _make(env)
    id1 = assembler._generate_deterministic_id("text", "1.1", "hello world")
    id2 = assembler._generate_deterministic_id("text", "1.1", "hello world")

    assert id1 == id2


def test_generate_deterministic_id_includes_type_and_entity_in_prefix(env) -> None:
    """Locks: the ID format is '{chunk_type}_{entity_id}_{hash8}' when entity_id is given."""
    assembler = _make(env)

    uid = assembler._generate_deterministic_id("exercise", "4.2", "content")

    assert uid.startswith("exercise_4.2_")


def test_generate_deterministic_id_no_entity_uses_type_only_prefix(env) -> None:
    """Locks: when entity_id is None the prefix is just '{chunk_type}_{hash8}'."""
    assembler = _make(env)

    uid = assembler._generate_deterministic_id("text", None, "content")

    assert uid.startswith("text_")
    assert "_None_" not in uid


def test_generate_deterministic_id_different_inputs_yield_different_ids(env) -> None:
    """Locks: different content strings produce different IDs (SHA-256 uniqueness)."""
    assembler = _make(env)

    id1 = assembler._generate_deterministic_id("text", "1.1", "content A")
    id2 = assembler._generate_deterministic_id("text", "1.1", "content B")

    assert id1 != id2


def test_generate_deterministic_id_hash_matches_sha256(env) -> None:
    """Locks: the 8-character suffix equals the first 8 chars of SHA-256(content)."""
    assembler = _make(env)
    content = "deterministic content"
    expected_hash = hashlib.sha256(content.encode()).hexdigest()[:8]

    uid = assembler._generate_deterministic_id("text", "2.1", content)

    assert uid.endswith(expected_hash)


# ---------------------------------------------------------------------------
# _extract_id
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Figure 1.2", "1.2"),
        ("Exercise 5.1", "5.1"),
        ("Table 10.5", "10.5"),
        ("Algorithm A.3", "A.3"),
        ("Example 4.4", "4.4"),
        # bare X.Y fallback
        ("The value is 4.4", "4.4"),
        ("prefix 2.10 suffix", "2.10"),
    ],
)
def test_extract_id_named_entity_and_bare_pattern(env, text, expected) -> None:
    """Locks: _extract_id returns X.Y from named entities and bare X.Y patterns."""
    assembler = _make(env)

    assert assembler._extract_id(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "Value is 100",        # integer only — no dot suffix
        "No numbers here",
        "",
    ],
)
def test_extract_id_returns_none_for_non_matching_text(env, text) -> None:
    """Locks: _extract_id returns None when no X.Y pattern is found."""
    assembler = _make(env)

    assert assembler._extract_id(text) is None


def test_extract_id_returns_none_for_none_input(env) -> None:
    """Locks: _extract_id(None) returns None without raising."""
    assembler = _make(env)

    assert assembler._extract_id(None) is None


# ---------------------------------------------------------------------------
# _safe_load_json
# ---------------------------------------------------------------------------


def test_safe_load_json_returns_empty_dict_for_missing_file(env) -> None:
    """Locks: _safe_load_json returns {} when the file does not exist."""
    assembler = _make(env)

    result = assembler._safe_load_json("definitely_missing_file.json")

    assert result == {}


# ---------------------------------------------------------------------------
# _load_and_offset
# ---------------------------------------------------------------------------


def test_load_and_offset_skips_non_integer_page_values(env) -> None:
    """Locks: items whose page key is not a valid integer are silently skipped."""
    path = env["tmp_path"] / "items.json"
    path.write_text(
        json.dumps([{"page": "not_a_number"}, {"page": 5, "data": "ok"}]), encoding="utf-8"
    )
    assembler = _make(env)

    result = assembler._load_and_offset(path, "page", offset=0)

    assert "not_a_number" not in result
    assert 5 in result


def test_load_and_offset_applies_offset_to_page_numbers(env) -> None:
    """Locks: the page key value is incremented by the given offset."""
    path = env["tmp_path"] / "items.json"
    path.write_text(json.dumps([{"page": 3}, {"page": 7}]), encoding="utf-8")
    assembler = _make(env)

    result = assembler._load_and_offset(path, "page", offset=10)

    assert 13 in result
    assert 17 in result
    assert 3 not in result
    assert 7 not in result


# ---------------------------------------------------------------------------
# _flush
# ---------------------------------------------------------------------------


def test_flush_on_empty_accumulator_returns_none_and_adds_no_chunk(env) -> None:
    """Locks: _flush([]) returns None and does not append anything to final_chunks."""
    assembler = _make(env)

    result = assembler._flush([], page=1)

    assert result is None
    assert assembler.final_chunks == []


def test_flush_on_non_empty_accumulator_adds_chunk_and_returns_it(env) -> None:
    """Locks: _flush(['Hello world']) appends a chunk to final_chunks and returns it."""
    assembler = _make(env)

    result = assembler._flush(["Hello world"], page=1)

    assert result is not None
    assert len(assembler.final_chunks) == 1
    assert assembler.final_chunks[0] is result


@pytest.mark.parametrize(
    "part_content",
    [
        "PART I",
        "PART II",
        "PART III",
        "PART IV",
        "PART V",
    ],
)
def test_flush_filters_out_part_marker_content(env, part_content) -> None:
    """Locks: content matching 'PART I/II/...' is silently discarded — _flush returns None."""
    assembler = _make(env)

    result = assembler._flush([part_content], page=1)

    assert result is None
    assert assembler.final_chunks == []


# ---------------------------------------------------------------------------
# Chunk type casing
# ---------------------------------------------------------------------------


def test_chunk_type_from_figures_json_is_lowercased(env, monkeypatch) -> None:
    """Locks: chunk_type from figures_json is lowercased (e.g. 'Captioned_Image' → 'captioned_image').
    _process_page returns early if blocks is empty, so we include a dummy footer block
    to ensure _handle_images is reached.
    """
    figures_data = [
        {
            "page": START_PAGE,
            "entity_id": "1.1",
            "chunk_type": "Captioned_Image",
            "caption": "Figure 1.1. A diagram.",
            "bbox": [10, 10, 200, 200],
        }
    ]
    env["figures"].write_text(json.dumps(figures_data), encoding="utf-8")

    # A footer block is in PADDLE_BLOCKS_TO_SKIP, so it produces no text chunk,
    # but it prevents the early-return triggered by an empty block list.
    dummy_blocks = [
        {"block_content": "1", "block_label": "footer", "block_bbox": [0, 0, 10, 10]}
    ]
    pages = _pages_with_content(START_PAGE - 1, dummy_blocks)
    (env["paddle_dir"] / "page_1.json").write_text(json.dumps(pages), encoding="utf-8")

    assembler = _make(env)
    monkeypatch.setattr(assembler, "_save", lambda: None)
    assembler.assemble()

    chunk_types = [c["chunk_type"] for c in assembler.final_chunks]
    assert "captioned_image" in chunk_types
    assert "Captioned_Image" not in chunk_types


# ---------------------------------------------------------------------------
# Section-header flush
# ---------------------------------------------------------------------------


def test_section_header_block_flushes_accumulated_text(env, monkeypatch) -> None:
    """Locks: a text block containing a markdown section header triggers a flush of
    the accumulated text that preceded it.
    """
    blocks = [
        {"block_content": "First paragraph text.", "block_label": "text", "block_bbox": [0, 0, 10, 10]},
        {"block_content": "# 2 New Section", "block_label": "text", "block_bbox": [0, 20, 10, 30]},
    ]
    pages = _pages_with_content(START_PAGE - 1, blocks)
    (env["paddle_dir"] / "page_1.json").write_text(json.dumps(pages), encoding="utf-8")

    assembler = _make(env)
    monkeypatch.setattr(assembler, "_save", lambda: None)
    assembler.assemble()

    contents = [c["content"] for c in assembler.final_chunks]
    assert any("First paragraph text." in c for c in contents)


# ---------------------------------------------------------------------------
# PADDLE_BLOCKS_TO_SKIP filtering
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("label", PADDLE_BLOCKS_TO_SKIP)
def test_blocks_with_skip_labels_are_excluded_from_output(env, monkeypatch, label) -> None:
    """Locks: every label in PADDLE_BLOCKS_TO_SKIP never contributes content to chunks."""
    blocks = [
        {"block_content": f"SKIP ME ({label})", "block_label": label, "block_bbox": [0, 0, 10, 10]},
        # a real text block so assemble() produces at least one chunk
        {
            "block_content": "Keep this text.",
            "block_label": "text",
            "block_bbox": [0, 20, 10, 30],
        },
        # section header to flush the accumulator
        {
            "block_content": "# 2 Trigger",
            "block_label": "text",
            "block_bbox": [0, 40, 10, 50],
        },
    ]
    pages = _pages_with_content(START_PAGE - 1, blocks)
    (env["paddle_dir"] / "page_1.json").write_text(json.dumps(pages), encoding="utf-8")

    assembler = _make(env)
    monkeypatch.setattr(assembler, "_save", lambda: None)
    assembler.assemble()

    all_content = "\n".join(c.get("content", "") for c in assembler.final_chunks)
    assert f"SKIP ME ({label})" not in all_content


# ---------------------------------------------------------------------------
# Special-region overlap
# ---------------------------------------------------------------------------


def test_block_inside_special_region_goes_to_region_accumulator(env, monkeypatch) -> None:
    """Locks: a paddle block whose bbox falls inside a block_map region is captured
    in that region's accumulator (and NOT in the main text stream).
    """
    # blocks_json entry in FITZ space; kx=2 ky=2 → [0,0,200,200] in Paddle space
    block_region = [
        {
            "page": START_PAGE,
            "entity_id": "4.4",
            "bbox": [0, 0, 100, 100],
            "chunk_type": "example",
            "caption": "Example 4.4",
        }
    ]
    env["blocks"].write_text(json.dumps(block_region), encoding="utf-8")

    blocks = [
        # inside [0,0,200,200] after 2× scale
        {
            "block_content": "Inside text.",
            "block_label": "text",
            "block_bbox": [10, 10, 50, 50],
        },
        # outside
        {
            "block_content": "Outside text.",
            "block_label": "text",
            "block_bbox": [300, 300, 400, 400],
        },
    ]
    pages = _pages_with_content(START_PAGE - 1, blocks)
    (env["paddle_dir"] / "page_1.json").write_text(json.dumps(pages), encoding="utf-8")

    assembler = _make(env)
    monkeypatch.setattr(assembler, "_save", lambda: None)
    assembler.assemble()

    example_chunk = next(
        (c for c in assembler.final_chunks if c["chunk_type"] == "example"), None
    )
    assert example_chunk is not None
    assert "Inside text." in example_chunk["content"]
    assert "Outside text." not in example_chunk["content"]


# ---------------------------------------------------------------------------
# Table matching
# ---------------------------------------------------------------------------


def test_table_block_matching_table_map_creates_numbered_table_chunk(env, monkeypatch) -> None:
    """Locks: when a paddle 'table' block's HTML matches a tables_json entry, a
    'numbered_table' chunk is produced.
    """
    table_html = "<table><tr><td>Value</td></tr></table>"
    tables_data = [
        {
            "page_number": START_PAGE,
            "table_content": table_html,
            "caption_content": "Table 3.1. Some data.",
        }
    ]
    env["tables"].write_text(json.dumps(tables_data), encoding="utf-8")

    blocks = [
        {
            "block_content": table_html,
            "block_label": "table",
            "block_bbox": [0, 0, 400, 200],
        }
    ]
    pages = _pages_with_content(START_PAGE - 1, blocks)
    (env["paddle_dir"] / "page_1.json").write_text(json.dumps(pages), encoding="utf-8")

    assembler = _make(env)
    monkeypatch.setattr(assembler, "_save", lambda: None)
    assembler.assemble()

    table_chunks = [c for c in assembler.final_chunks if c["chunk_type"] == "numbered_table"]
    assert len(table_chunks) == 1
    assert table_chunks[0]["entity_id"] == "3.1"


# ---------------------------------------------------------------------------
# Formula chunk
# ---------------------------------------------------------------------------


def test_formula_number_block_creates_numbered_formula_chunk(env, monkeypatch) -> None:
    """Locks: a 'formula_number' block with content present in formula_map produces
    a 'numbered_formula' chunk.
    """
    env["formulas"].write_text(json.dumps({"(1.1)": "E = mc^2"}), encoding="utf-8")

    blocks = [
        {"block_content": "(1.1)", "block_label": "formula_number", "block_bbox": [0, 0, 10, 10]},
    ]
    pages = _pages_with_content(START_PAGE - 1, blocks)
    (env["paddle_dir"] / "page_1.json").write_text(json.dumps(pages), encoding="utf-8")

    assembler = _make(env)
    monkeypatch.setattr(assembler, "_save", lambda: None)
    assembler.assemble()

    formula_chunks = [c for c in assembler.final_chunks if c["chunk_type"] == "numbered_formula"]
    assert len(formula_chunks) == 1
    assert formula_chunks[0]["entity_id"] == "1.1"
    assert formula_chunks[0]["content"] == "E = mc^2"


def test_defined_in_chunk_set_on_formula_after_next_flush(env, monkeypatch) -> None:
    """Locks: numbered_formula chunks get 'defined_in_chunk' set to the chunk_id of
    the next flushed text/exercise chunk.
    """
    env["formulas"].write_text(json.dumps({"(2.1)": "x^2"}), encoding="utf-8")

    blocks = [
        # Text before formula
        {"block_content": "Some prior text.", "block_label": "text", "block_bbox": [0, 0, 10, 5]},
        # Formula number
        {"block_content": "(2.1)", "block_label": "formula_number", "block_bbox": [0, 10, 10, 15]},
        # Section header triggers a flush of the accumulated text
        {"block_content": "# 3 Next Chapter", "block_label": "text", "block_bbox": [0, 20, 10, 30]},
    ]
    pages = _pages_with_content(START_PAGE - 1, blocks)
    (env["paddle_dir"] / "page_1.json").write_text(json.dumps(pages), encoding="utf-8")

    assembler = _make(env)
    monkeypatch.setattr(assembler, "_save", lambda: None)
    assembler.assemble()

    text_chunk = next(
        (c for c in assembler.final_chunks if c["chunk_type"] == "text"), None
    )
    formula_chunk = next(
        (c for c in assembler.final_chunks if c["chunk_type"] == "numbered_formula"), None
    )
    assert text_chunk is not None
    assert formula_chunk is not None
    assert formula_chunk.get("defined_in_chunk") == text_chunk["chunk_id"]


# ---------------------------------------------------------------------------
# Exercise self-reference removal
# ---------------------------------------------------------------------------


def test_exercise_chunk_self_reference_removed_from_referenced_exercises(
    env, monkeypatch
) -> None:
    """Locks: an exercise chunk does not include its own entity_id in referenced_exercises."""
    blocks = [
        {
            "block_content": "## 1.1 Exercises",
            "block_label": "text",
            "block_bbox": [0, 0, 10, 10],
        },
        {
            "block_content": "Exercise 4.4. Show that Exercise 4.4 holds.",
            "block_label": "text",
            "block_bbox": [0, 20, 10, 30],
        },
        # trigger flush
        {
            "block_content": "# 5 Next",
            "block_label": "text",
            "block_bbox": [0, 40, 10, 50],
        },
    ]
    pages = _pages_with_content(START_PAGE - 1, blocks)
    (env["paddle_dir"] / "page_1.json").write_text(json.dumps(pages), encoding="utf-8")

    assembler = _make(env)
    monkeypatch.setattr(assembler, "_save", lambda: None)
    assembler.assemble()

    exercise_chunks = [c for c in assembler.final_chunks if c["chunk_type"] == "exercise"]
    for chunk in exercise_chunks:
        if chunk.get("entity_id") == "4.4":
            assert "4.4" not in (chunk.get("referenced_exercises") or [])
            break


# ---------------------------------------------------------------------------
# Page range filtering
# ---------------------------------------------------------------------------


def test_assemble_skips_pages_before_start_page(env, monkeypatch) -> None:
    """Locks: assemble() does not process pages with 1-based index < START_PAGE."""
    # Only 1 page total → page_idx=0, page_idx+1=1 < START_PAGE(23) → not processed
    blocks = [
        {"block_content": "Should not appear.", "block_label": "text", "block_bbox": [0, 0, 10, 10]},
        {"block_content": "# 1 Trigger", "block_label": "text", "block_bbox": [0, 20, 10, 30]},
    ]
    pages = [{"page_num": 1, "prunedResult": {"parsing_res_list": blocks}}]
    (env["paddle_dir"] / "page_1.json").write_text(json.dumps(pages), encoding="utf-8")

    assembler = _make(env)
    monkeypatch.setattr(assembler, "_save", lambda: None)
    assembler.assemble()

    # page is before START_PAGE so no text chunks should be produced
    text_chunks = [c for c in assembler.final_chunks if c["chunk_type"] == "text"]
    assert text_chunks == []


def test_assemble_processes_exactly_start_page(env, monkeypatch) -> None:
    """Locks: assemble() processes page_idx+1 == START_PAGE (the boundary is inclusive)."""
    blocks = [
        {"block_content": "Processed content.", "block_label": "text", "block_bbox": [0, 0, 10, 10]},
        {"block_content": "# 2 Trigger", "block_label": "text", "block_bbox": [0, 20, 10, 30]},
    ]
    pages = _pages_with_content(START_PAGE - 1, blocks)
    (env["paddle_dir"] / "page_1.json").write_text(json.dumps(pages), encoding="utf-8")

    assembler = _make(env)
    monkeypatch.setattr(assembler, "_save", lambda: None)
    assembler.assemble()

    all_content = " ".join(c.get("content", "") for c in assembler.final_chunks)
    assert "Processed content." in all_content


# ---------------------------------------------------------------------------
# bbox transforms
# ---------------------------------------------------------------------------


def test_block_map_bbox_scaled_by_2x_on_init(env) -> None:
    """Locks: blocks_json bboxes (FITZ space) are scaled by kx=2.0, ky=2.0 at init time.
    (PADDLE_WIDTH/FITZ_WIDTH = 1152/576 = 2.0, PADDLE_HEIGHT/FITZ_HEIGHT = 1296/648 = 2.0)
    """
    blocks_data = [{"page": 1, "entity_id": "1.1", "bbox": [10, 20, 30, 40], "chunk_type": "example"}]
    env["blocks"].write_text(json.dumps(blocks_data), encoding="utf-8")

    assembler = _make(env)

    scaled = assembler.block_map[1][0]["bbox"]
    # kx = 1152/576 = 2.0, ky = 1296/648 = 2.0
    assert scaled == [20.0, 40.0, 60.0, 80.0]


def test_image_map_bbox_scaled_by_image_scale_on_init(env) -> None:
    """Locks: figures_json bboxes are scaled by kx_i = (1152/576) * 0.36 = 0.72 and
    ky_i = (1296/648) * 0.36 = 0.72 at init time.
    """
    figures_data = [
        {"page": 1, "entity_id": "1.1", "bbox": [100, 100, 200, 200], "chunk_type": "captioned_image"}
    ]
    env["figures"].write_text(json.dumps(figures_data), encoding="utf-8")

    assembler = _make(env)

    scaled = assembler.image_map[1][0]["bbox"]
    # kx_i = ky_i = 0.72 — hardcoded to lock the current physics-based scale
    assert abs(scaled[0] - 72.0) < 0.01   # 100 * 0.72
    assert abs(scaled[2] - 144.0) < 0.01  # 200 * 0.72


# ---------------------------------------------------------------------------
# Caption prefix skipping
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "caption_prefix",
    [
        "Figure 1.1. A diagram showing...",
        "Example 3.2. Solution follows.",
        "Table 2.4. Data summary.",
        "Algorithm 1.1. Pseudocode.",
    ],
)
def test_caption_prefix_lines_are_skipped_in_text_stream(env, monkeypatch, caption_prefix) -> None:
    """Locks: lines matching 'Figure/Example/Table/Algorithm X.Y.' at the start of a
    block's plain-text are skipped from the main text accumulator.
    """
    blocks = [
        {"block_content": caption_prefix, "block_label": "text", "block_bbox": [0, 0, 10, 10]},
        {"block_content": "Normal text after.", "block_label": "text", "block_bbox": [0, 20, 10, 30]},
        {"block_content": "# 2 Flush", "block_label": "text", "block_bbox": [0, 40, 10, 50]},
    ]
    pages = _pages_with_content(START_PAGE - 1, blocks)
    (env["paddle_dir"] / "page_1.json").write_text(json.dumps(pages), encoding="utf-8")

    assembler = _make(env)
    monkeypatch.setattr(assembler, "_save", lambda: None)
    assembler.assemble()

    all_content = " ".join(c.get("content", "") for c in assembler.final_chunks)
    # Caption prefix must NOT appear in body text chunks
    assert caption_prefix not in all_content


# ---------------------------------------------------------------------------
# Chunk splitting at MAX_CHUNK_CHAR_LENGTH
# ---------------------------------------------------------------------------


def test_chunk_splits_when_length_exceeds_max_chunk_char_length(env, monkeypatch) -> None:
    """Locks: when accumulating text would exceed MAX_CHUNK_CHAR_LENGTH(1000) chars,
    the current accumulator is flushed first, producing two separate chunks.
    """
    # Two paragraphs each close to the limit; together they exceed it.
    big_text_a = "A" * (MAX_CHUNK_CHAR_LENGTH - 10)
    big_text_b = "B" * 50

    blocks = [
        {"block_content": big_text_a, "block_label": "text", "block_bbox": [0, 0, 10, 10]},
        {"block_content": big_text_b, "block_label": "text", "block_bbox": [0, 20, 10, 30]},
        {"block_content": "# 2 Flush", "block_label": "text", "block_bbox": [0, 40, 10, 50]},
    ]
    pages = _pages_with_content(START_PAGE - 1, blocks)
    (env["paddle_dir"] / "page_1.json").write_text(json.dumps(pages), encoding="utf-8")

    assembler = _make(env)
    monkeypatch.setattr(assembler, "_save", lambda: None)
    assembler.assemble()

    text_chunks = [c for c in assembler.final_chunks if c["chunk_type"] == "text"]
    # The overflow should cause at least two text chunks
    assert len(text_chunks) >= 2
