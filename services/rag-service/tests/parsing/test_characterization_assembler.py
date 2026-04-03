"""
Characterization tests for DocumentAssembler.

These tests lock the *current* behaviour so that future refactors cannot
silently break it.  Every test carries a docstring stating the invariant.
"""

import hashlib
import json

import pytest
from pipeline.parsing.main import BBOX_PADDING  # noqa: F401 — imported to lock the value at 5
from pipeline.parsing.main import (
    MAX_CHUNK_CHAR_LENGTH,
    PADDLE_BLOCKS_TO_SKIP,
    START_PAGE,
    DocumentAssembler,
)

from .test_main_assembler import _with_block_ids

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
    pages = [{"page_num": i + 1, "prunedResult": {"parsing_res_list": []}} for i in range(n_blank)]
    pages.append(
        {
            "page_num": n_blank + 1,
            "prunedResult": {"parsing_res_list": _with_block_ids(page_blocks)},
        }
    )
    return pages


# ---------------------------------------------------------------------------
# Spatial containment (via special-region capture)
# ---------------------------------------------------------------------------


def test_block_at_padding_boundary_is_captured_in_special_region(env, monkeypatch) -> None:
    """Locks: a paddle block whose bbox right/bottom edge equals region_edge + BBOX_PADDING(5)
    IS captured in the special region; a block 1 pixel beyond that boundary is NOT captured
    and ends up in the main text stream instead.
    """
    block_region = [
        {
            "page": START_PAGE,
            "entity_id": "1.1",
            "bbox": [0, 0, 100, 100],  # FITZ → Paddle [0,0,200,200] after 2× scale
            "chunk_type": "example",
            "caption": "",
        }
    ]
    env["blocks"].write_text(json.dumps(block_region), encoding="utf-8")

    blocks = [
        # b1[2]=205 <= b2[2]+5=205 → _is_inside True → captured in region
        {
            "block_content": "At boundary text.",
            "block_label": "text",
            "block_bbox": [0, 0, 205, 205],
        },
        # b1[2]=206 > 205 → _is_inside False → goes to main text stream
        {
            "block_content": "Outside block text.",
            "block_label": "text",
            "block_bbox": [0, 0, 206, 206],
        },
    ]
    pages = _pages_with_content(START_PAGE - 1, blocks)
    (env["paddle_dir"] / "page_1.json").write_text(json.dumps(pages), encoding="utf-8")

    assembler = _make(env)
    monkeypatch.setattr(assembler, "_save", lambda: None)
    assembler.assemble()

    example_chunk = next((c for c in assembler.final_chunks if c["chunk_type"] == "example"), None)
    assert example_chunk is not None
    assert "At boundary text." in example_chunk["content"]
    assert "Outside block text." not in example_chunk["content"]
    text_chunks = [c for c in assembler.final_chunks if c["chunk_type"] == "text"]
    assert any("Outside block text." in c["content"] for c in text_chunks)


def test_block_completely_outside_region_goes_to_main_stream(env, monkeypatch) -> None:
    """Locks: a paddle block with bbox completely outside all special regions goes to the
    main text accumulator and appears in a text chunk, not in any example chunk.
    """
    block_region = [
        {
            "page": START_PAGE,
            "entity_id": "3.3",
            "bbox": [0, 0, 100, 100],  # FITZ → Paddle [0,0,200,200]
            "chunk_type": "example",
            "caption": "",
        }
    ]
    env["blocks"].write_text(json.dumps(block_region), encoding="utf-8")

    blocks = [
        {
            "block_content": "Example 3.3. Region caption.",
            "block_label": "text",
            "block_bbox": [0, 0, 10, 10],
        },
        {
            "block_content": "Far outside text.",
            "block_label": "text",
            "block_bbox": [500, 500, 600, 600],
        },
    ]
    pages = _pages_with_content(START_PAGE - 1, blocks)
    (env["paddle_dir"] / "page_1.json").write_text(json.dumps(pages), encoding="utf-8")

    assembler = _make(env)
    monkeypatch.setattr(assembler, "_save", lambda: None)
    assembler.assemble()

    example_chunk = next((c for c in assembler.final_chunks if c["chunk_type"] == "example"), None)
    if example_chunk:
        assert "Far outside text." not in example_chunk["content"]
    all_content = " ".join(c.get("content", "") for c in assembler.final_chunks)
    assert "Far outside text." in all_content


# ---------------------------------------------------------------------------
# Deterministic chunk IDs (via assemble())
# ---------------------------------------------------------------------------


def test_chunk_ids_are_stable_for_identical_inputs(env, monkeypatch) -> None:
    """Locks: two separate DocumentAssembler runs over identical file inputs produce
    exactly the same chunk_id list in the same order.
    """
    blocks = [
        {
            "block_content": "Stable text content.",
            "block_label": "text",
            "block_bbox": [0, 0, 10, 10],
        },
        {"block_content": "# 2 Trigger", "block_label": "text", "block_bbox": [0, 20, 10, 30]},
    ]
    pages = _pages_with_content(START_PAGE - 1, blocks)
    (env["paddle_dir"] / "page_1.json").write_text(json.dumps(pages), encoding="utf-8")

    assembler1 = _make(env)
    monkeypatch.setattr(assembler1, "_save", lambda: None)
    assembler1.assemble()

    assembler2 = _make(env)
    monkeypatch.setattr(assembler2, "_save", lambda: None)
    assembler2.assemble()

    ids1 = [c["chunk_id"] for c in assembler1.final_chunks]
    ids2 = [c["chunk_id"] for c in assembler2.final_chunks]
    assert ids1 == ids2


def test_chunk_id_starts_with_chunk_type_prefix(env, monkeypatch) -> None:
    """Locks: every chunk_id in final_chunks starts with '<chunk_type>_'."""
    blocks = [
        {"block_content": "Type prefix text.", "block_label": "text", "block_bbox": [0, 0, 10, 10]},
        {"block_content": "# 2 Flush", "block_label": "text", "block_bbox": [0, 20, 10, 30]},
    ]
    pages = _pages_with_content(START_PAGE - 1, blocks)
    (env["paddle_dir"] / "page_1.json").write_text(json.dumps(pages), encoding="utf-8")

    assembler = _make(env)
    monkeypatch.setattr(assembler, "_save", lambda: None)
    assembler.assemble()

    for chunk in assembler.final_chunks:
        assert chunk["chunk_id"].startswith(chunk["chunk_type"] + "_")


def test_chunks_with_different_content_have_different_ids(env, monkeypatch) -> None:
    """Locks: two text chunks with distinct content strings produce distinct chunk_ids."""
    blocks = [
        {
            "block_content": "Alpha content text.",
            "block_label": "text",
            "block_bbox": [0, 0, 10, 10],
        },
        {"block_content": "# 2 Flush", "block_label": "text", "block_bbox": [0, 20, 10, 30]},
        {
            "block_content": "Beta content text.",
            "block_label": "text",
            "block_bbox": [0, 40, 10, 50],
        },
        {"block_content": "# 3 Flush", "block_label": "text", "block_bbox": [0, 60, 10, 70]},
    ]
    pages = _pages_with_content(START_PAGE - 1, blocks)
    (env["paddle_dir"] / "page_1.json").write_text(json.dumps(pages), encoding="utf-8")

    assembler = _make(env)
    monkeypatch.setattr(assembler, "_save", lambda: None)
    assembler.assemble()

    text_chunks = [c for c in assembler.final_chunks if c["chunk_type"] == "text"]
    assert len(text_chunks) >= 2
    ids = [c["chunk_id"] for c in text_chunks]
    assert len(set(ids)) == len(ids)


def test_chunk_id_hash_suffix_is_sha256_of_content(env, monkeypatch) -> None:
    """Locks: the 8-char hash suffix in chunk_id equals SHA-256(content)[:8], where
    content is the exact string stored in the chunk (text type has no post-processing).
    """
    known_content = "Deterministic paragraph."

    blocks = [
        {"block_content": known_content, "block_label": "text", "block_bbox": [0, 0, 10, 10]},
        {"block_content": "# 2 Flush", "block_label": "text", "block_bbox": [0, 20, 10, 30]},
    ]
    pages = _pages_with_content(START_PAGE - 1, blocks)
    (env["paddle_dir"] / "page_1.json").write_text(json.dumps(pages), encoding="utf-8")

    assembler = _make(env)
    monkeypatch.setattr(assembler, "_save", lambda: None)
    assembler.assemble()

    text_chunk = next((c for c in assembler.final_chunks if c["chunk_type"] == "text"), None)
    assert text_chunk is not None
    expected_hash = hashlib.sha256(known_content.encode()).hexdigest()[:8]
    assert text_chunk["chunk_id"].endswith(expected_hash)


# ---------------------------------------------------------------------------
# entity_id extraction (via assemble())
# ---------------------------------------------------------------------------


def test_entity_id_extracted_from_named_entity_in_text(env, monkeypatch) -> None:
    """Locks: a text chunk whose content contains 'Figure X.Y' (or similar named entity)
    has entity_id set to the X.Y part extracted by _extract_id.
    """
    blocks = [
        {
            "block_content": "See Figure 1.2 above.",
            "block_label": "text",
            "block_bbox": [0, 0, 10, 10],
        },
        {"block_content": "# 2 Flush", "block_label": "text", "block_bbox": [0, 20, 10, 30]},
    ]
    pages = _pages_with_content(START_PAGE - 1, blocks)
    (env["paddle_dir"] / "page_1.json").write_text(json.dumps(pages), encoding="utf-8")

    assembler = _make(env)
    monkeypatch.setattr(assembler, "_save", lambda: None)
    assembler.assemble()

    text_chunk = next((c for c in assembler.final_chunks if c["chunk_type"] == "text"), None)
    assert text_chunk is not None
    assert text_chunk["entity_id"] == "1.2"


def test_entity_id_extracted_from_bare_number_pattern_in_text(env, monkeypatch) -> None:
    """Locks: a text chunk whose content contains a bare 'X.Y' pattern (no named keyword)
    has entity_id set to that X.Y value.
    """
    blocks = [
        {"block_content": "The value is 4.4.", "block_label": "text", "block_bbox": [0, 0, 10, 10]},
        {"block_content": "# 2 Flush", "block_label": "text", "block_bbox": [0, 20, 10, 30]},
    ]
    pages = _pages_with_content(START_PAGE - 1, blocks)
    (env["paddle_dir"] / "page_1.json").write_text(json.dumps(pages), encoding="utf-8")

    assembler = _make(env)
    monkeypatch.setattr(assembler, "_save", lambda: None)
    assembler.assemble()

    text_chunk = next((c for c in assembler.final_chunks if c["chunk_type"] == "text"), None)
    assert text_chunk is not None
    assert text_chunk["entity_id"] == "4.4"


def test_entity_id_is_none_when_content_has_no_id_pattern(env, monkeypatch) -> None:
    """Locks: a text chunk whose content has no X.Y pattern at all has entity_id=None."""
    blocks = [
        {"block_content": "Plain text no ID.", "block_label": "text", "block_bbox": [0, 0, 10, 10]},
        {"block_content": "# 2 Flush", "block_label": "text", "block_bbox": [0, 20, 10, 30]},
    ]
    pages = _pages_with_content(START_PAGE - 1, blocks)
    (env["paddle_dir"] / "page_1.json").write_text(json.dumps(pages), encoding="utf-8")

    assembler = _make(env)
    monkeypatch.setattr(assembler, "_save", lambda: None)
    assembler.assemble()

    text_chunk = next((c for c in assembler.final_chunks if c["chunk_type"] == "text"), None)
    assert text_chunk is not None
    assert text_chunk["entity_id"] is None


# ---------------------------------------------------------------------------
# Formula map loading (safe_load_json via assemble())
# ---------------------------------------------------------------------------


def test_empty_formula_map_produces_no_formula_chunks(env, monkeypatch) -> None:
    """Locks: when formulas.json is an empty mapping, a formula_number block does not
    produce any numbered_formula chunk because 'content in self.formula_map' is False.
    """
    env["formulas"].write_text(json.dumps({}), encoding="utf-8")

    blocks = [
        {"block_content": "(1.1)", "block_label": "formula_number", "block_bbox": [0, 0, 10, 10]},
    ]
    pages = _pages_with_content(START_PAGE - 1, blocks)
    (env["paddle_dir"] / "page_1.json").write_text(json.dumps(pages), encoding="utf-8")

    assembler = _make(env)
    monkeypatch.setattr(assembler, "_save", lambda: None)
    assembler.assemble()

    formula_chunks = [c for c in assembler.final_chunks if c["chunk_type"] == "numbered_formula"]
    assert formula_chunks == []


# ---------------------------------------------------------------------------
# Page-number loading and offset (via assemble())
# ---------------------------------------------------------------------------


def test_blocks_json_entry_with_invalid_page_is_silently_ignored(env, monkeypatch) -> None:
    """Locks: a blocks_json entry with a non-integer page value is silently skipped so
    its region is never created, while a valid entry on the same page is respected.
    """
    block_regions = [
        # non-integer page — must be skipped
        {
            "page": "bad_page",
            "entity_id": "9.9",
            "bbox": [0, 0, 100, 100],
            "chunk_type": "example",
            "caption": "",
        },
        # valid entry — must create a region
        {
            "page": START_PAGE,
            "entity_id": "2.2",
            "bbox": [200, 200, 250, 250],  # FITZ → Paddle [400,400,500,500]
            "chunk_type": "example",
            "caption": "",
        },
    ]
    env["blocks"].write_text(json.dumps(block_regions), encoding="utf-8")

    blocks = [
        # inside the bad_page region bbox (if it existed) — should go to main text
        {
            "block_content": "Should be main text.",
            "block_label": "text",
            "block_bbox": [10, 10, 50, 50],
        },
        # inside the valid region bbox
        {
            "block_content": "Captured in region.",
            "block_label": "text",
            "block_bbox": [410, 410, 480, 480],
        },
    ]
    pages = _pages_with_content(START_PAGE - 1, blocks)
    (env["paddle_dir"] / "page_1.json").write_text(json.dumps(pages), encoding="utf-8")

    assembler = _make(env)
    monkeypatch.setattr(assembler, "_save", lambda: None)
    assembler.assemble()

    entity_ids = [c.get("entity_id") for c in assembler.final_chunks]
    assert "9.9" not in entity_ids
    assert "2.2" in entity_ids


def test_blocks_json_entry_applies_to_correct_page(env, monkeypatch) -> None:
    """Locks: a blocks_json entry at page=START_PAGE creates a region that captures
    paddle blocks on that page — confirming page numbers are applied without offset.
    """
    block_regions = [
        {
            "page": START_PAGE,
            "entity_id": "3.3",
            "bbox": [0, 0, 100, 100],  # FITZ → Paddle [0,0,200,200]
            "chunk_type": "example",
            "caption": "",
        }
    ]
    env["blocks"].write_text(json.dumps(block_regions), encoding="utf-8")

    blocks = [
        {
            "block_content": "Inside region block.",
            "block_label": "text",
            "block_bbox": [10, 10, 50, 50],
        },
    ]
    pages = _pages_with_content(START_PAGE - 1, blocks)
    (env["paddle_dir"] / "page_1.json").write_text(json.dumps(pages), encoding="utf-8")

    assembler = _make(env)
    monkeypatch.setattr(assembler, "_save", lambda: None)
    assembler.assemble()

    example_chunk = next((c for c in assembler.final_chunks if c.get("entity_id") == "3.3"), None)
    assert example_chunk is not None
    assert "Inside region block." in example_chunk["content"]


# ---------------------------------------------------------------------------
# Accumulator flushing (via assemble())
# ---------------------------------------------------------------------------


def test_page_with_only_skipped_blocks_produces_no_text_chunks(env, monkeypatch) -> None:
    """Locks: a page whose every block has a label in PADDLE_BLOCKS_TO_SKIP never
    contributes to the text accumulator, so assemble() produces no text chunks.
    """
    blocks = [
        {"block_content": "1", "block_label": "footer", "block_bbox": [0, 0, 10, 10]},
    ]
    pages = _pages_with_content(START_PAGE - 1, blocks)
    (env["paddle_dir"] / "page_1.json").write_text(json.dumps(pages), encoding="utf-8")

    assembler = _make(env)
    monkeypatch.setattr(assembler, "_save", lambda: None)
    assembler.assemble()

    text_chunks = [c for c in assembler.final_chunks if c["chunk_type"] == "text"]
    assert text_chunks == []


def test_text_block_with_section_header_triggers_flush(env, monkeypatch) -> None:
    """Locks: a section-header block causes any preceding accumulated text to be flushed
    into a text chunk that is appended to final_chunks.
    """
    blocks = [
        {
            "block_content": "Accumulated content text.",
            "block_label": "text",
            "block_bbox": [0, 0, 10, 10],
        },
        {"block_content": "# 2 New Section", "block_label": "text", "block_bbox": [0, 20, 10, 30]},
    ]
    pages = _pages_with_content(START_PAGE - 1, blocks)
    (env["paddle_dir"] / "page_1.json").write_text(json.dumps(pages), encoding="utf-8")

    assembler = _make(env)
    monkeypatch.setattr(assembler, "_save", lambda: None)
    assembler.assemble()

    text_chunks = [c for c in assembler.final_chunks if c["chunk_type"] == "text"]
    assert len(text_chunks) >= 1
    assert any("Accumulated content text." in c["content"] for c in text_chunks)


def test_part_marker_text_block_does_not_produce_chunk(env, monkeypatch) -> None:
    """Locks: content exactly matching 'PART I/II/III/...' is discarded by _flush
    (is_part_chunk check) and never appears in any chunk's content.
    """
    blocks = [
        {"block_content": "PART II", "block_label": "text", "block_bbox": [0, 0, 10, 10]},
        {"block_content": "# 2 New Section", "block_label": "text", "block_bbox": [0, 20, 10, 30]},
    ]
    pages = _pages_with_content(START_PAGE - 1, blocks)
    (env["paddle_dir"] / "page_1.json").write_text(json.dumps(pages), encoding="utf-8")

    assembler = _make(env)
    monkeypatch.setattr(assembler, "_save", lambda: None)
    assembler.assemble()

    all_content = " ".join(c.get("content", "") for c in assembler.final_chunks)
    assert "PART II" not in all_content


# ---------------------------------------------------------------------------
# Chunk type casing
# ---------------------------------------------------------------------------


def test_chunk_type_from_figures_json_is_lowercased(env, monkeypatch) -> None:
    """Locks: chunk_type from figures_json is lowercased (e.g.'Captioned_Image'→'captioned_image').
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
    dummy_blocks = [{"block_content": "1", "block_label": "footer", "block_bbox": [0, 0, 10, 10]}]
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
        {
            "block_content": "First paragraph text.",
            "block_label": "text",
            "block_bbox": [0, 0, 10, 10],
        },
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

    example_chunk = next((c for c in assembler.final_chunks if c["chunk_type"] == "example"), None)
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

    text_chunk = next((c for c in assembler.final_chunks if c["chunk_type"] == "text"), None)
    formula_chunk = next(
        (c for c in assembler.final_chunks if c["chunk_type"] == "numbered_formula"), None
    )
    assert text_chunk is not None
    assert formula_chunk is not None
    assert formula_chunk.get("defined_in_chunk") == text_chunk["chunk_id"]


# ---------------------------------------------------------------------------
# Exercise self-reference removal
# ---------------------------------------------------------------------------


def test_exercise_chunk_self_reference_removed_from_referenced_exercises(env, monkeypatch) -> None:
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
        {
            "block_content": "Should not appear.",
            "block_label": "text",
            "block_bbox": [0, 0, 10, 10],
        },
        {"block_content": "# 1 Trigger", "block_label": "text", "block_bbox": [0, 20, 10, 30]},
    ]
    pages = [{"page_num": 1, "prunedResult": {"parsing_res_list": _with_block_ids(blocks)}}]
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
        {
            "block_content": "Processed content.",
            "block_label": "text",
            "block_bbox": [0, 0, 10, 10],
        },
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
    blocks_data = [
        {"page": 1, "entity_id": "1.1", "bbox": [10, 20, 30, 40], "chunk_type": "example"}
    ]
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
        {
            "page": 1,
            "entity_id": "1.1",
            "bbox": [100, 100, 200, 200],
            "chunk_type": "captioned_image",
        }
    ]
    env["figures"].write_text(json.dumps(figures_data), encoding="utf-8")

    assembler = _make(env)

    scaled = assembler.image_map[1][0]["bbox"]
    # kx_i = ky_i = 0.72 — hardcoded to lock the current physics-based scale
    assert abs(scaled[0] - 72.0) < 0.01  # 100 * 0.72
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
        {
            "block_content": "Normal text after.",
            "block_label": "text",
            "block_bbox": [0, 20, 10, 30],
        },
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


# ---------------------------------------------------------------------------
# Metadata snapshotting and Part transitions
# ---------------------------------------------------------------------------


def test_exercise_at_end_of_part_is_flushed_with_correct_metadata(env, monkeypatch) -> None:
    """Locks: when a 'PART' title is encountered, any accumulated text (like an exercise)
    is flushed BEFORE the metadata extractor updates to the new part.
    """
    blocks_init = [
        {"block_content": "PART I", "block_label": "doc_title", "block_bbox": [0, 0, 10, 10]},
    ]
    blocks_p1 = [
        {"block_content": "## 1.1 Exercises", "block_label": "text", "block_bbox": [0, 0, 10, 10]},
        {
            "block_content": "Exercise 1.1. End of Part I.",
            "block_label": "text",
            "block_bbox": [0, 20, 10, 30],
        },
    ]
    blocks_p2 = [
        {"block_content": "PART II", "block_label": "doc_title", "block_bbox": [0, 0, 10, 10]},
        {"block_content": "# 2 New Chapter", "block_label": "text", "block_bbox": [0, 20, 10, 30]},
    ]

    # Prepend blank pages to reach START_PAGE
    pages = [
        {"page_num": i + 1, "prunedResult": {"parsing_res_list": []}} for i in range(START_PAGE - 1)
    ]
    pages.extend(
        [
            {
                "page_num": START_PAGE,
                "prunedResult": {"parsing_res_list": _with_block_ids(blocks_init + blocks_p1)},
            },
            {
                "page_num": START_PAGE + 1,
                "prunedResult": {"parsing_res_list": _with_block_ids(blocks_p2)},
            },
        ]
    )
    (env["paddle_dir"] / "page_1.json").write_text(json.dumps(pages), encoding="utf-8")

    assembler = _make(env)
    monkeypatch.setattr(assembler, "_save", lambda: None)
    # Mock set_part to track call order if needed, but here we check final chunks
    assembler.assemble()

    ex_chunk = next((c for c in assembler.final_chunks if "End of Part I" in c["content"]), None)
    assert ex_chunk is not None
    assert ex_chunk["chunk_type"] == "exercise"
    # It should still have Part I metadata because it was flushed before PART II update
    assert ex_chunk["part"] == "I"


def test_metadata_snapshot_prevents_pollution_from_next_section_header(env, monkeypatch) -> None:
    """Locks: the use of .copy() for prev_meta ensures that a chunk flushed by a new
    section header receives the hierarchy state of the preceding content, not the new section.
    """
    blocks = [
        {"block_content": "# 1 Old Section", "block_label": "text", "block_bbox": [0, 0, 10, 10]},
        {
            "block_content": "Content of section 1.",
            "block_label": "text",
            "block_bbox": [0, 20, 10, 30],
        },
        {"block_content": "# 2 New Section", "block_label": "text", "block_bbox": [0, 40, 10, 50]},
    ]
    pages = _pages_with_content(START_PAGE - 1, blocks)
    (env["paddle_dir"] / "page_1.json").write_text(json.dumps(pages), encoding="utf-8")

    assembler = _make(env)
    monkeypatch.setattr(assembler, "_save", lambda: None)
    assembler.assemble()

    chunk = next(
        (c for c in assembler.final_chunks if "Content of section 1" in c["content"]), None
    )
    assert chunk is not None
    # If snapshotting works, section_number is 1.
    # If it was polluted by the next block, it would be 2.
    assert str(chunk["section_number"]) == "1"
    assert chunk["section_title"].strip().lower() == "old section"
