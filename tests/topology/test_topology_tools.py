from __future__ import annotations

from contextlib import contextmanager
from uuid import uuid4

import pytest
from environment_api.smart_query_builder.tools import topology_tools
from pydantic import ValidationError


@contextmanager
def _fake_session_ctx(session: object):
    yield session


def test_list_warehouses_returns_tool_result_with_meta(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_session = object()
    warehouse_id = uuid4()

    rows = [
        {
            "id": warehouse_id,
            "name": "WH-TOPO-001",
            "region": "EU-WEST",
            "tz": "UTC",
        }
    ]

    monkeypatch.setattr(topology_tools, "get_session", lambda: _fake_session_ctx(fake_session))
    monkeypatch.setattr(topology_tools, "fetch_warehouse_rows", lambda session, request: rows)

    result = topology_tools.list_warehouses(region="EU-WEST", limit=5, offset=2)

    assert len(result.data.warehouses) == 1
    assert result.data.warehouses[0].id == warehouse_id
    assert result.message == "Retrieved 1 warehouses."
    assert result.meta["count"] == 1
    assert result.meta["filters"]["region"] == "EU-WEST"
    assert result.meta["pagination"] == {"limit": 5, "offset": 2}


def test_get_locations_tree_builds_nested_structure(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_session = object()
    warehouse_id = uuid4()
    root_id = uuid4()
    child_id = uuid4()

    monkeypatch.setattr(topology_tools, "get_session", lambda: _fake_session_ctx(fake_session))
    monkeypatch.setattr(
        topology_tools,
        "fetch_warehouse_row",
        lambda session, request: {
            "id": warehouse_id,
            "name": "WH-TOPO-001",
            "region": "EU-WEST",
            "tz": "UTC",
        },
    )
    monkeypatch.setattr(
        topology_tools,
        "fetch_warehouse_location_rows",
        lambda session, request: [
            {
                "id": root_id,
                "warehouse_id": warehouse_id,
                "parent_location_id": None,
                "code": "ROOT",
                "type": "VIRTUAL",
                "capacity_units": 100,
            },
            {
                "id": child_id,
                "warehouse_id": warehouse_id,
                "parent_location_id": root_id,
                "code": "CHILD",
                "type": "SHELF",
                "capacity_units": 50,
            },
        ],
    )

    result = topology_tools.get_locations_tree(str(warehouse_id))

    assert result.data.node_count == 2
    assert result.data.root_count == 1
    assert result.data.roots[0].id == root_id
    assert result.data.roots[0].children[0].id == child_id


def test_get_capacity_utilization_snapshot_requires_time_mode() -> None:
    with pytest.raises(
        RuntimeError,
        match="Unable to get capacity utilization snapshot.",
    ) as excinfo:
        topology_tools.get_capacity_utilization_snapshot(warehouse_id=str(uuid4()))

    assert isinstance(excinfo.value.__cause__, ValidationError)

