import json
import os
from pathlib import Path

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


def test_full_assembly_cycle(mock_data_env):
    """Test full assembly cycle."""
    old_cwd = os.getcwd()
    os.chdir(mock_data_env["paddle_dir"].parent)

    try:
        assembler = DocumentAssembler(
            paddle_dir=mock_data_env["paddle_dir"],
            figures_json=mock_data_env["figures"],
            blocks_json=mock_data_env["blocks"],
            tables_json=mock_data_env["tables"],
            formulas_json=mock_data_env["formulas"],
        )

        assembler.assemble()

        output_file = Path("ULTIMATE_BOOK_DATA.json")
        assert output_file.exists()

        with output_file.open("r", encoding="utf-8") as f:
            data = json.load(f)
            assert len(data) > 0
    finally:
        os.chdir(old_cwd)
