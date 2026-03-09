from __future__ import annotations

from contextlib import contextmanager
from uuid import uuid4

import pytest
from environment_api.smart_query_builder.tools import observed_inventory_tools
from pydantic import ValidationError


@contextmanager
def _fake_session_ctx(session: object):
    yield session


def test_get_observed_inventory_snapshot_dev_mode_returns_ground_truth_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_session = object()
    product_id = uuid4()
    location_id = uuid4()
    device_id = uuid4()

    monkeypatch.setattr(
        observed_inventory_tools,
        "get_session",
        lambda: _fake_session_ctx(fake_session),
    )
    monkeypatch.setattr(
        observed_inventory_tools,
        "fetch_observed_inventory_snapshot_rows",
        lambda session, request: [
            {
                "product_id": product_id,
                "location_id": location_id,
                "observed_qty": 10.0,
                "confidence": 0.9,
                "device_id": device_id,
                "quality_status": "ok",
                "on_hand": 11.0,
                "reserved": 1.0,
            }
        ],
    )

    result = observed_inventory_tools.get_observed_inventory_snapshot(
        quality_status_in=["ok"],
        dev_mode=True,
    )

    assert len(result.data) == 1
    row = result.data[0]
    assert row.product_id == product_id
    assert row.quality_status.value == "ok"
    assert row.on_hand == 11.0
    assert result.message == "Retrieved 1 observed inventory rows."
    assert result.meta["filters"]["quality_status_in"] == ["ok"]
    assert result.meta["filters"]["dev_mode"] is True


def test_get_observed_inventory_snapshot_non_dev_mode_returns_public_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        observed_inventory_tools,
        "get_session",
        lambda: _fake_session_ctx(object()),
    )
    monkeypatch.setattr(
        observed_inventory_tools,
        "fetch_observed_inventory_snapshot_rows",
        lambda session, request: [
            {
                "product_id": uuid4(),
                "location_id": uuid4(),
                "observed_qty": None,
                "confidence": None,
                "device_id": uuid4(),
                "quality_status": "damaged",
                "on_hand": 100.0,
                "reserved": 10.0,
            }
        ],
    )

    result = observed_inventory_tools.get_observed_inventory_snapshot(
        quality_status_in=["damaged"],
        dev_mode=False,
    )

    assert len(result.data) == 1
    row = result.data[0]
    assert row.quality_status.value == "damaged"
    assert row.observed_qty is None
    assert row.confidence is None
    assert result.meta["filters"]["dev_mode"] is False


def test_get_observed_inventory_snapshot_wraps_validation_error() -> None:
    with pytest.raises(
        RuntimeError,
        match="Unable to get observed inventory snapshot.",
    ) as excinfo:
        observed_inventory_tools.get_observed_inventory_snapshot(quality_status_in=["not-a-status"])

    assert isinstance(excinfo.value.__cause__, ValidationError)
