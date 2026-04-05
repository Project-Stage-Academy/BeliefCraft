from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from environment_api.smart_query_builder.tools import procurement_tools
from pydantic import ValidationError


@contextmanager
def _fake_session_ctx(session: object):
    yield session


def test_list_suppliers_returns_tool_result_with_meta(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_session = object()
    rows = [
        {
            "id": uuid4(),
            "name": "Acme Supply",
            "reliability_score": 0.91,
            "region": "EU-WEST",
        }
    ]

    monkeypatch.setattr(procurement_tools, "get_session", lambda: _fake_session_ctx(fake_session))
    monkeypatch.setattr(procurement_tools, "fetch_supplier_rows", lambda session, request: rows)

    result = procurement_tools.list_suppliers(region="EU-WEST", limit=5, offset=2)

    assert len(result.data.suppliers) == 1
    assert result.data.suppliers[0].name == "Acme Supply"
    assert result.message == "Retrieved 1 suppliers."
    assert result.meta.count == 1
    assert result.meta.filters["region"] == "EU-WEST"
    assert result.meta.pagination is not None
    assert result.meta.pagination.limit == 5
    assert result.meta.pagination.offset == 2


def test_list_suppliers_wraps_validation_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(procurement_tools, "get_session", lambda: _fake_session_ctx(object()))

    with pytest.raises(RuntimeError, match="Unable to list suppliers.") as excinfo:
        procurement_tools.list_suppliers(reliability_min=0.9, reliability_max=0.1)

    assert isinstance(excinfo.value.__cause__, ValidationError)


def test_list_purchase_orders_serializes_statuses_in_meta(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(procurement_tools, "get_session", lambda: _fake_session_ctx(object()))
    monkeypatch.setattr(procurement_tools, "fetch_purchase_order_rows", lambda session, request: [])

    result = procurement_tools.list_purchase_orders(
        status_in=["submitted", "partial"],
        created_after=datetime(2026, 2, 1, tzinfo=UTC),
        include_names=True,
        limit=10,
    )

    assert result.data.purchase_orders == []
    assert result.message == "No purchase orders matched filters."
    assert result.meta.filters["status_in"] == ["submitted", "partial"]
    assert result.meta.filters["include_names"] is True
    assert result.meta.pagination is not None
    assert result.meta.pagination.limit == 10
    assert result.meta.pagination.offset == 0
