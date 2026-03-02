from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from environment_api.smart_query_builder.tools import inventory_history_tools
from pydantic import ValidationError


@contextmanager
def _fake_session_ctx(session: object):
    yield session


def test_list_inventory_moves_returns_tool_result_with_meta(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_session = object()
    now = datetime.now(UTC)
    rows = [
        {
            "id": uuid4(),
            "product_id": uuid4(),
            "from_location_id": uuid4(),
            "to_location_id": None,
            "move_type": "adjustment",
            "qty": 5.0,
            "occurred_at": now,
            "reason_code": "cycle_count_gain",
            "reported_qty": 5.0,
            "actual_qty": 5.0,
        }
    ]

    monkeypatch.setattr(
        inventory_history_tools, "get_session", lambda: _fake_session_ctx(fake_session)
    )
    monkeypatch.setattr(
        inventory_history_tools, "fetch_inventory_move_rows", lambda session, request: rows
    )

    result = inventory_history_tools.list_inventory_moves(
        warehouse_id="wh-1",
        product_id="prod-1",
        move_type="adjustment",
        limit=10,
        offset=5,
    )

    assert len(result.data.moves) == 1
    assert result.data.moves[0].reason_code == "cycle_count_gain"
    assert result.message == "Retrieved 1 inventory moves."
    assert result.meta["count"] == 1
    assert result.meta["filters"]["warehouse_id"] == "wh-1"
    assert result.meta["pagination"] == {"limit": 10, "offset": 5}


def test_list_inventory_moves_wraps_validation_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        inventory_history_tools, "get_session", lambda: _fake_session_ctx(object())
    )

    with pytest.raises(RuntimeError, match="Unable to list inventory moves.") as excinfo:
        inventory_history_tools.list_inventory_moves(
            from_ts=datetime(2026, 3, 10, tzinfo=UTC),
            to_ts=datetime(2026, 3, 1, tzinfo=UTC),
        )

    assert isinstance(excinfo.value.__cause__, ValidationError)


def test_get_inventory_move_success(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_session = object()
    move_id = str(uuid4())
    now = datetime.now(UTC)
    row = {
        "id": uuid4(),
        "product_id": uuid4(),
        "from_location_id": uuid4(),
        "to_location_id": None,
        "move_type": "transfer",
        "qty": 7.0,
        "occurred_at": now,
        "reason_code": None,
        "reported_qty": None,
        "actual_qty": None,
    }

    monkeypatch.setattr(
        inventory_history_tools, "get_session", lambda: _fake_session_ctx(fake_session)
    )
    monkeypatch.setattr(
        inventory_history_tools,
        "fetch_inventory_move_row",
        lambda session, request: row,
    )

    result = inventory_history_tools.get_inventory_move(move_id=move_id)

    assert result.data.move.qty == 7.0
    assert result.message == "Retrieved inventory move details."
    assert result.meta["move_id"] == move_id


def test_get_inventory_move_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        inventory_history_tools, "get_session", lambda: _fake_session_ctx(object())
    )
    monkeypatch.setattr(
        inventory_history_tools,
        "fetch_inventory_move_row",
        lambda session, request: None,
    )

    with pytest.raises(RuntimeError, match="Unable to get inventory move.") as excinfo:
        inventory_history_tools.get_inventory_move(move_id=str(uuid4()))

    assert isinstance(excinfo.value.__cause__, ValueError)


def test_get_inventory_move_audit_trace_with_observations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_session = object()
    move_id = str(uuid4())
    now = datetime.now(UTC)
    move_row = {
        "id": uuid4(),
        "product_id": uuid4(),
        "from_location_id": uuid4(),
        "to_location_id": None,
        "move_type": "transfer",
        "qty": 4.0,
        "occurred_at": now,
        "reason_code": None,
        "reported_qty": None,
        "actual_qty": None,
    }
    observation_rows = [
        {
            "id": uuid4(),
            "observed_at": now,
            "product_id": uuid4(),
            "location_id": uuid4(),
            "obs_type": "balance",
            "observed_qty": 3.5,
            "confidence": 0.9,
        }
    ]

    monkeypatch.setattr(
        inventory_history_tools, "get_session", lambda: _fake_session_ctx(fake_session)
    )
    monkeypatch.setattr(
        inventory_history_tools,
        "fetch_inventory_move_audit_trace_rows",
        lambda session, request: (move_row, observation_rows),
    )

    result = inventory_history_tools.get_inventory_move_audit_trace(move_id=move_id)

    assert result.data.move.qty == 4.0
    assert len(result.data.observations) == 1
    assert result.meta["observation_count"] == 1


def test_get_inventory_adjustments_summary_builds_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_session = object()
    summary_row = {"count": 3, "total_qty": 9.0}
    breakdown_rows = [
        {"reason_code": "cycle_count_gain", "count": 2, "total_qty": 6.0},
        {"reason_code": "cycle_count_loss", "count": 1, "total_qty": 3.0},
    ]

    monkeypatch.setattr(
        inventory_history_tools, "get_session", lambda: _fake_session_ctx(fake_session)
    )
    monkeypatch.setattr(
        inventory_history_tools,
        "fetch_inventory_adjustments_summary",
        lambda session, request: (summary_row, breakdown_rows),
    )

    result = inventory_history_tools.get_inventory_adjustments_summary(
        warehouse_id="wh-1",
        product_id="prod-1",
    )

    assert result.data.count == 3
    assert result.data.total_qty == 9.0
    assert len(result.data.by_reason) == 2
    assert result.meta["filters"]["warehouse_id"] == "wh-1"
    assert result.message == "Aggregated 3 inventory adjustments."

