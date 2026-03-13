"""
Unit tests for services/rag-service/src/scripts/store_code_schema.py
"""

import json
import logging
from unittest.mock import MagicMock, patch

from rag_scripts.store_code_schema import (
    main,
    setup_collections,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_collection_mock(existing_ref_names: list[str] | None = None):
    """Lightweight mock of a Weaviate Collection."""
    col = MagicMock()
    refs = []
    for n in existing_ref_names or []:
        r = MagicMock()
        r.name = n
        refs.append(r)
    col.config.get.return_value.references = refs
    return col


def _make_batch_collection_mock():
    """Collection mock with a working batch context manager."""
    col = MagicMock()
    batch = MagicMock()
    col.batch.dynamic.return_value.__enter__ = MagicMock(return_value=batch)
    col.batch.dynamic.return_value.__exit__ = MagicMock(return_value=False)
    return col, batch


# ---------------------------------------------------------------------------
# setup_collections
# ---------------------------------------------------------------------------


def _build_client_mock():
    """Client mock where all collections start as non-existent."""
    client = MagicMock()
    client.collections.exists.return_value = False
    col_cls = _make_collection_mock([])
    col_mth = _make_collection_mock([])
    col_fn = _make_collection_mock([])

    def use_side_effect(name):
        return {"CodeClass": col_cls, "CodeMethod": col_mth, "CodeFunction": col_fn}.get(
            name, MagicMock()
        )

    client.collections.use.side_effect = use_side_effect
    return client


def test_setup_collections_creates_three_collections():
    client = _build_client_mock()
    setup_collections(client, recreate=False)
    assert client.collections.create.call_count == 3


def test_setup_collections_returns_three_collection_objects():
    client = _build_client_mock()
    result = setup_collections(client, recreate=False)
    assert len(result) == 3


def test_setup_collections_recreate_deletes_all_three():
    client = _build_client_mock()
    client.collections.exists.return_value = True
    setup_collections(client, recreate=True)
    assert client.collections.delete.call_count == 3


def test_setup_collections_does_not_create_when_collections_already_exist():
    client = _build_client_mock()
    client.collections.exists.return_value = True
    setup_collections(client, recreate=False)
    client.collections.create.assert_not_called()


# ---------------------------------------------------------------------------
# main()
# ---------------------------------------------------------------------------


def _fake_algorithms():
    return [
        {
            "algorithm_number": "Algorithm 1.1.",
            "code": "class Foo:\n    def run(self): pass\n",
            "description": "test",
            "declarations": {},
        }
    ]


def _fake_examples():
    return [{"example_number": "Example 1.1.", "text": "Use Foo().", "description": ""}]


@patch("scripts.store_code_schema.weaviate.connect_to_local")
@patch("scripts.store_code_schema.build_code_schema")
def test_main_runs_without_error(mock_build_schema, mock_connect, tmp_path):
    alg_file = tmp_path / "algs.json"
    alg_file.write_text(json.dumps(_fake_algorithms()))
    ex_file = tmp_path / "exs.json"
    ex_file.write_text(json.dumps(_fake_examples()))

    mock_build_schema.return_value = {"classes": [], "methods": [], "functions": []}
    client = MagicMock()
    client.collections.exists.return_value = False
    client.collections.use.return_value = _make_collection_mock([])
    mock_connect.return_value.__enter__ = MagicMock(return_value=client)
    mock_connect.return_value.__exit__ = MagicMock(return_value=False)

    with patch(
        "sys.argv",
        [
            "store_code_schema.py",
            "--algorithms_file_path",
            str(alg_file),
            "--examples_file_path",
            str(ex_file),
        ],
    ):
        main()  # Should not raise


@patch("scripts.store_code_schema.weaviate.connect_to_local")
@patch("scripts.store_code_schema.build_code_schema")
def test_main_exits_gracefully_on_bad_algorithms_file(
    mock_build_schema, mock_connect, tmp_path, caplog
):
    with (
        caplog.at_level(logging.ERROR),
        patch(
            "sys.argv",
            ["store_code_schema.py", "--algorithms_file_path", str(tmp_path / "missing.json")],
        ),
    ):
        main()

    assert any("Failed to load" in r.message for r in caplog.records)
    mock_build_schema.assert_not_called()
    mock_connect.assert_not_called()


@patch("scripts.store_code_schema.weaviate.connect_to_local")
@patch("scripts.store_code_schema.build_code_schema")
def test_main_exits_gracefully_on_bad_examples_file(
    mock_build_schema, mock_connect, tmp_path, caplog
):
    alg_file = tmp_path / "algs.json"
    alg_file.write_text(json.dumps(_fake_algorithms()))

    with (
        caplog.at_level(logging.ERROR),
        patch(
            "sys.argv",
            [
                "store_code_schema.py",
                "--algorithms_file_path",
                str(alg_file),
                "--examples_file_path",
                str(tmp_path / "missing.json"),
            ],
        ),
    ):
        main()

    assert any("Failed to load" in r.message for r in caplog.records)
    mock_build_schema.assert_not_called()
    mock_connect.assert_not_called()


@patch("scripts.store_code_schema.weaviate.connect_to_local")
@patch("scripts.store_code_schema.build_code_schema")
def test_main_skips_example_refs_when_examples_list_is_empty(
    mock_build_schema, mock_connect, tmp_path
):
    alg_file = tmp_path / "algs.json"
    alg_file.write_text(json.dumps(_fake_algorithms()))
    ex_file = tmp_path / "exs.json"
    ex_file.write_text("[]")

    mock_build_schema.return_value = {"classes": [], "methods": [], "functions": []}
    client = MagicMock()
    client.collections.exists.return_value = False
    client.collections.use.return_value = _make_collection_mock([])
    mock_connect.return_value.__enter__ = MagicMock(return_value=client)
    mock_connect.return_value.__exit__ = MagicMock(return_value=False)

    with patch(
        "sys.argv",
        [
            "store_code_schema.py",
            "--algorithms_file_path",
            str(alg_file),
            "--examples_file_path",
            str(ex_file),
        ],
    ):
        main()

    # When examples list is empty, unified_collection should never be fetched for example refs
    used_names = [c.args[0] for c in client.collections.use.call_args_list if c.args]
    assert "unified_collection" not in used_names
