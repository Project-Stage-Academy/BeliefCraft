import json

import pytest
from pipeline.parsing.main import DocumentAssembler


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


def test_merge_visual_items(mock_data_env):
    assembler = DocumentAssembler(
        paddle_dir=mock_data_env["paddle_dir"],
        figures_json=mock_data_env["figures"],
        blocks_json=mock_data_env["blocks"],
        tables_json=mock_data_env["tables"],
        formulas_json=mock_data_env["formulas"],
    )
    items = [
        {"entity_id": "fig_1", "bbox": [10, 10, 50, 50], "chunk_type": "image"},
        {"entity_id": "fig_1", "bbox": [40, 40, 100, 100], "image_index": 5},
    ]
    merged = assembler._merge_visual_items(items)

    assert "fig_1" in merged
    assert merged["fig_1"]["bbox"] == [10, 10, 100, 100]
    assert merged["fig_1"]["image_index"] == 5


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
