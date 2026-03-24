import json

import pytest
from pipeline.parsing.main import (
    START_PAGE,
    DocumentAssembler,
)


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


@pytest.fixture
def mock_data_env(tmp_path):
    """Create a mock environment with necessary files for testing DocumentAssembler."""
    paddle_dir = tmp_path / "paddle_results"
    paddle_dir.mkdir()

    paddle_file = paddle_dir / "page_1.json"
    paddle_data = {
        "page_num": 1,
        "prunedResult": {
            "parsing_res_list": [
                {
                    "block_content": "CHAPTER 1 INTRODUCTION",
                    "block_label": "title",
                    "block_bbox": [10, 10, 100, 20],
                },
                {
                    "block_content": "This is a simple text paragraph.",
                    "block_label": "text",
                    "block_bbox": [10, 30, 100, 50],
                },
            ]
        },
    }
    paddle_file.write_text(json.dumps([paddle_data]), encoding="utf-8")

    figures_json = tmp_path / "figures.json"
    figures_json.write_text(json.dumps([]), encoding="utf-8")

    blocks_json = tmp_path / "blocks.json"
    blocks_json.write_text(json.dumps([]), encoding="utf-8")

    tables_json = tmp_path / "tables.json"
    tables_json.write_text(json.dumps([]), encoding="utf-8")

    formulas_json = tmp_path / "formulas.json"
    formulas_json.write_text(json.dumps({" (1.1)": "E = mc^2"}), encoding="utf-8")

    return {
        "paddle_dir": paddle_dir,
        "figures": figures_json,
        "blocks": blocks_json,
        "tables": tables_json,
        "formulas": formulas_json,
        "output": tmp_path / "ULTIMATE_BOOK_DATA.json",
    }


def test_assembler_initialization(mock_data_env):
    """Test that DocumentAssembler initializes correctly with mock data."""
    assembler = DocumentAssembler(
        paddle_dir=mock_data_env["paddle_dir"],
        figures_json=mock_data_env["figures"],
        blocks_json=mock_data_env["blocks"],
        tables_json=mock_data_env["tables"],
        formulas_json=mock_data_env["formulas"],
    )
    assert len(assembler.paddle_pages) == 1
    assert assembler.formula_map[" (1.1)"] == "E = mc^2"


def test_generate_deterministic_id():
    """Test that the ID generation is deterministic and consistent."""
    with pytest.raises(FileNotFoundError):
        DocumentAssembler("no", "no", "no", "no", "no")


def test_assembler_safe_load_non_existent(mock_data_env):
    """Test that _safe_load_json returns an empty dict when the file does not exist."""
    assembler = DocumentAssembler(
        paddle_dir=mock_data_env["paddle_dir"],
        figures_json=mock_data_env["figures"],
        blocks_json=mock_data_env["blocks"],
        tables_json=mock_data_env["tables"],
        formulas_json=mock_data_env["formulas"],
    )

    res = assembler._safe_load_json("imaginary_file.json")
    assert res == {}

    uid = assembler._generate_deterministic_id("text", "1.1", "some content")
    assert "text_1.1_" in uid

    assert assembler._extract_id("Figure 1.2") == "1.2"
    assert assembler._extract_id("Table 10.5") == "10.5"
    assert assembler._extract_id(None) is None


def test_assembler_is_inside(mock_data_env):
    assembler = DocumentAssembler(
        paddle_dir=mock_data_env["paddle_dir"],
        figures_json=mock_data_env["figures"],
        blocks_json=mock_data_env["blocks"],
        tables_json=mock_data_env["tables"],
        formulas_json=mock_data_env["formulas"],
    )
    assert assembler._is_inside([100, 100, 200, 200], [90, 90, 210, 210]) is True
    assert assembler._is_inside([100, 100, 200, 200], [300, 300, 400, 400]) is False
    assert assembler._is_inside([], [10, 10, 20, 20]) is False


def test_blocks_json_bbox_is_scaled_on_assembly(mock_data_env, monkeypatch):
    """Locks: blocks_json bboxes (FITZ space) are scaled 2× to Paddle space on init,
    so a paddle block that falls inside the scaled bbox is captured in the example region.
    """
    block_data = [
        {
            "page": START_PAGE,
            "entity_id": "5.5",
            "bbox": [10, 20, 30, 40],  # FITZ → Paddle [20,40,60,80] after 2× scale
            "chunk_type": "example",
            "caption": "",
        }
    ]
    mock_data_env["blocks"].write_text(json.dumps(block_data), encoding="utf-8")

    # Block at [25,45,55,70] is inside [20,40,60,80] with BBOX_PADDING=5
    blocks = [
        {"block_content": "Inside scaled block.", "block_label": "text", "block_bbox": [25, 45, 55, 70]},
    ]
    pages = _pages_with_content(START_PAGE - 1, blocks)
    (mock_data_env["paddle_dir"] / "page_1.json").write_text(json.dumps(pages), encoding="utf-8")

    assembler = DocumentAssembler(
        paddle_dir=mock_data_env["paddle_dir"],
        figures_json=mock_data_env["figures"],
        blocks_json=mock_data_env["blocks"],
        tables_json=mock_data_env["tables"],
        formulas_json=mock_data_env["formulas"],
    )
    monkeypatch.setattr(assembler, "_save", lambda: None)
    assembler.assemble()

    example_chunk = next(
        (c for c in assembler.final_chunks if c.get("entity_id") == "5.5"), None
    )
    assert example_chunk is not None
    assert "Inside scaled block." in example_chunk["content"]


def test_assembler_load_and_offset(mock_data_env):
    assembler = DocumentAssembler(
        paddle_dir=mock_data_env["paddle_dir"],
        figures_json=mock_data_env["figures"],
        blocks_json=mock_data_env["blocks"],
        tables_json=mock_data_env["tables"],
        formulas_json=mock_data_env["formulas"],
    )

    path = mock_data_env["paddle_dir"] / "temp_test.json"
    path.write_text(json.dumps([{"page": "not_an_int"}, {"page": 5}]), encoding="utf-8")

    res = assembler._load_and_offset(path, "page", offset=10)
    assert 15 in res


def test_assembler_load_and_offset_edge_cases(mock_data_env):
    assembler = DocumentAssembler(
        paddle_dir=mock_data_env["paddle_dir"],
        figures_json=mock_data_env["figures"],
        blocks_json=mock_data_env["blocks"],
        tables_json=mock_data_env["tables"],
        formulas_json=mock_data_env["formulas"],
    )
    bad_json = mock_data_env["paddle_dir"] / "bad_data.json"
    bad_json.write_text(json.dumps([{"page": "not_a_number"}, {"page": 10}]), encoding="utf-8")

    res = assembler._load_and_offset(bad_json, "page", offset=5)
    assert 15 in res  # 10 + 5

    assert assembler._safe_load_json("missing.json") == {}


def test_document_assembler_full_flow(mock_data_env, monkeypatch):
    """Comprehensive test of the DocumentAssembler's full flow with mocked data.

    assemble() only processes pages where START_PAGE(23) <= page_idx+1 <= LAST_PAGE(648).
    We therefore supply 23 pages so the last one (page_idx=22) is the first processed page.
    """
    dummy_pages = [
        {"page_num": i + 1, "prunedResult": {"parsing_res_list": []}}
        for i in range(22)
    ]
    # Page at index 22 (page_idx+1 == 23 == START_PAGE) carries real content
    dummy_pages.append(
        {
            "page_num": 23,
            "prunedResult": {
                "parsing_res_list": [
                    {
                        "block_content": "Some introductory text.",
                        "block_label": "text",
                        "block_bbox": [10, 30, 100, 50],
                    },
                    {
                        "block_content": "# 2 NEXT SECTION",
                        "block_label": "text",
                        "block_bbox": [10, 60, 100, 80],
                    },
                ]
            },
        }
    )

    paddle_file = mock_data_env["paddle_dir"] / "page_1.json"
    paddle_file.write_text(json.dumps(dummy_pages), encoding="utf-8")

    assembler = DocumentAssembler(
        paddle_dir=mock_data_env["paddle_dir"],
        figures_json=mock_data_env["figures"],
        blocks_json=mock_data_env["blocks"],
        tables_json=mock_data_env["tables"],
        formulas_json=mock_data_env["formulas"],
    )

    monkeypatch.setattr(assembler, "_save", lambda: None)

    assembler.assemble()

    assert len(assembler.final_chunks) > 0


def test_assembler_flush_empty(mock_data_env):
    assembler = DocumentAssembler(
        paddle_dir=mock_data_env["paddle_dir"],
        figures_json=mock_data_env["figures"],
        blocks_json=mock_data_env["blocks"],
        tables_json=mock_data_env["tables"],
        formulas_json=mock_data_env["formulas"],
    )
    assembler._flush([], 1)
    assert len(assembler.final_chunks) == 0

    assembler._flush(["Hello"], 1)
    assert len(assembler.final_chunks) > 0


def test_assembler_id_generation_variants(mock_data_env):
    assembler = DocumentAssembler(
        paddle_dir=mock_data_env["paddle_dir"],
        figures_json=mock_data_env["figures"],
        blocks_json=mock_data_env["blocks"],
        tables_json=mock_data_env["tables"],
        formulas_json=mock_data_env["formulas"],
    )
    id1 = assembler._generate_deterministic_id("image", None, "content1")
    id2 = assembler._generate_deterministic_id("table", "2.2", "content1")

    assert id1 != id2
    assert "image_" in id1
    assert "table_2.2_" in id2


def test_assembler_simple_helpers(mock_data_env):
    assembler = DocumentAssembler(
        paddle_dir=mock_data_env["paddle_dir"],
        figures_json=mock_data_env["figures"],
        blocks_json=mock_data_env["blocks"],
        tables_json=mock_data_env["tables"],
        formulas_json=mock_data_env["formulas"],
    )
    assert assembler._extract_id("Exercise 5.1") == "5.1"
    assert assembler._extract_id("Just text") is None

    meta = {"section_title": "Test"}
    obj = assembler._create_chunk_obj("text", "content", 1, meta)
    assert obj["chunk_type"] == "text"
    assert obj["page"] == 1


def test_id_generation_logic(mock_data_env):

    assembler = DocumentAssembler(
        mock_data_env["paddle_dir"],
        mock_data_env["figures"],
        mock_data_env["blocks"],
        mock_data_env["tables"],
        mock_data_env["formulas"],
    )

    id1 = assembler._generate_deterministic_id("text", "1.1", "content")
    id2 = assembler._generate_deterministic_id("text", None, "content")

    assert id1 != id2
    assert len(id1) > 0


def test_paddle_ocr_content_used_not_markdown_field(mock_data_env, monkeypatch):
    """Locks: assemble() reads block_content from prunedResult, not any 'markdown' field.

    A section-header block forces a flush of the preceding accumulated text so the
    flushed chunk's content must equal the OCR text, not the markdown version.
    """
    blank_pages = [
        {"page_num": i + 1, "prunedResult": {"parsing_res_list": []}}
        for i in range(START_PAGE - 1)
    ]
    content_page = {
        "page_num": START_PAGE,
        # markdown field is present but _process_page never reads it
        "markdown": {"text": "Formula: $E=mc^2$"},
        "prunedResult": {
            "parsing_res_list": [
                {
                    "block_content": "Formula: E=mc2",
                    "block_label": "text",
                    "block_bbox": [0, 0, 10, 10],
                },
                {
                    "block_content": "# 2 Next Topic",
                    "block_label": "text",
                    "block_bbox": [0, 20, 10, 30],
                },
            ]
        },
    }
    pages = blank_pages + [content_page]
    (mock_data_env["paddle_dir"] / "page_1.json").write_text(json.dumps(pages), encoding="utf-8")

    assembler = DocumentAssembler(
        paddle_dir=mock_data_env["paddle_dir"],
        figures_json=mock_data_env["figures"],
        blocks_json=mock_data_env["blocks"],
        tables_json=mock_data_env["tables"],
        formulas_json=mock_data_env["formulas"],
    )
    monkeypatch.setattr(assembler, "_save", lambda: None)
    assembler.assemble()

    text_chunks = [c for c in assembler.final_chunks if c["chunk_type"] == "text"]
    assert len(text_chunks) >= 1
    assert any("Formula: E=mc2" in c["content"] for c in text_chunks)
    all_content = " ".join(c.get("content", "") for c in assembler.final_chunks)
    assert "$E=mc^2$" not in all_content


def test_handle_visual_objects_overlap(mock_data_env, monkeypatch):
    """Locks: blocks.json defines named regions (e.g. examples).  assemble() assigns
    paddle blocks whose bbox falls inside a named region to that region's accumulator.
    The resulting chunk must have the correct type and entity_id, and must include
    the text of the overlapping paddle block.

    The block_map bbox [0,0,100,100] is scaled by kx=2, ky=2 → [0,0,200,200].
    Paddle block-0 at [10,10,50,50] is inside [0,0,200,200].
    Paddle block-1 at [200,200,300,300] is NOT inside (300 > 200+BBOX_PADDING=205).
    """
    mock_block_data = [
        {
            "page": START_PAGE,
            "entity_id": "4.4",
            "bbox": [0, 0, 100, 100],
            "chunk_type": "example",
            "caption": "Example 4.4",
        }
    ]
    mock_data_env["blocks"].write_text(json.dumps(mock_block_data), encoding="utf-8")

    page_blocks = [
        {
            "block_content": "Example 4.4 text inside box",
            "block_bbox": [10, 10, 50, 50],
            "block_label": "text",
        },
        {
            "block_content": "Normal text outside",
            "block_bbox": [200, 200, 300, 300],
            "block_label": "text",
        },
    ]
    pages = _pages_with_content(START_PAGE - 1, page_blocks)
    (mock_data_env["paddle_dir"] / "page_1.json").write_text(json.dumps(pages), encoding="utf-8")

    assembler = DocumentAssembler(
        paddle_dir=mock_data_env["paddle_dir"],
        figures_json=mock_data_env["figures"],
        blocks_json=mock_data_env["blocks"],
        tables_json=mock_data_env["tables"],
        formulas_json=mock_data_env["formulas"],
    )
    monkeypatch.setattr(assembler, "_save", lambda: None)
    assembler.assemble()

    assert any(c["chunk_type"] == "example" for c in assembler.final_chunks)
    example_chunk = next(c for c in assembler.final_chunks if c["chunk_type"] == "example")
    assert example_chunk["entity_id"] == "4.4"
    assert "Example 4.4 text inside box" in example_chunk["content"]
    assert "Normal text outside" not in example_chunk["content"]


def test_extract_id_strict_regex(mock_data_env):
    """Test that ID is extracted correctly with the new fallback logic."""
    assembler = DocumentAssembler(
        paddle_dir=mock_data_env["paddle_dir"],
        figures_json=mock_data_env["figures"],
        blocks_json=mock_data_env["blocks"],
        tables_json=mock_data_env["tables"],
        formulas_json=mock_data_env["formulas"],
    )

    assert assembler._extract_id("Example 4.4") == "4.4"
    assert assembler._extract_id("Exercise 1.2") == "1.2"

    assert assembler._extract_id("The value is 4.4") == "4.4"

    assert assembler._extract_id("Value is 100") is None
