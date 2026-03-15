from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from common.schemas.devices import DeviceAnomalyType
from environment_api.smart_query_builder.tools import devices_tools


@contextmanager
def _fake_session_ctx(session: object):
    yield session


def test_list_sensor_devices_returns_tool_result_with_meta(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_session = object()
    warehouse_id = uuid4()
    device_id = uuid4()

    monkeypatch.setattr(devices_tools, "get_session", lambda: _fake_session_ctx(fake_session))
    monkeypatch.setattr(
        devices_tools,
        "fetch_sensor_device_rows",
        lambda session, request: [
            {
                "id": device_id,
                "warehouse_id": warehouse_id,
                "device_type": "camera",
                "noise_sigma": 0.1,
                "missing_rate": 0.02,
                "bias": 0.0,
                "status": "active",
            }
        ],
    )

    result = devices_tools.list_sensor_devices(
        warehouse_id=str(warehouse_id),
        device_type="camera",
        status="active",
    )

    assert len(result.data) == 1
    assert result.data[0].id == device_id
    assert result.message == "Retrieved 1 sensor devices."
    assert result.meta["count"] == 1
    assert result.meta["filters"]["warehouse_id"] == str(warehouse_id)
    assert result.meta["filters"]["device_type"] == "camera"
    assert result.meta["filters"]["status"] == "active"


def test_get_device_anomalies_detects_multiple_anomaly_types(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_session = object()

    monkeypatch.setattr(devices_tools, "get_session", lambda: _fake_session_ctx(fake_session))
    monkeypatch.setattr(
        devices_tools,
        "fetch_device_anomaly_candidate_rows",
        lambda session, request: [
            {
                "device_id": uuid4(),
                "warehouse_id": uuid4(),
                "status": "offline",
                "obs_count_window": 2,
                "missing_count_window": 1,
                "observed_missing_rate": 0.5,
                "configured_missing_rate": 0.1,
                "avg_confidence": 0.8,
            },
            {
                "device_id": uuid4(),
                "warehouse_id": uuid4(),
                "status": "active",
                "obs_count_window": 0,
                "missing_count_window": 0,
                "observed_missing_rate": None,
                "configured_missing_rate": 0.05,
                "avg_confidence": None,
            },
            {
                "device_id": uuid4(),
                "warehouse_id": uuid4(),
                "status": "active",
                "obs_count_window": 3,
                "missing_count_window": 0,
                "observed_missing_rate": 0.0,
                "configured_missing_rate": 0.2,
                "avg_confidence": 0.3,
            },
        ],
    )

    result = devices_tools.get_device_anomalies(window=24)

    assert len(result.data) == 3
    first = set(result.data[0].anomaly_types)
    assert DeviceAnomalyType.OFFLINE_WITH_OBSERVATIONS in first
    assert DeviceAnomalyType.MISSING_RATE_SPIKE in first

    second = set(result.data[1].anomaly_types)
    assert second == {DeviceAnomalyType.ONLINE_WITHOUT_OBSERVATIONS}

    third = set(result.data[2].anomaly_types)
    assert third == {DeviceAnomalyType.LOW_CONFIDENCE}


def test_get_sensor_device_not_found_wraps_value_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(devices_tools, "get_session", lambda: _fake_session_ctx(object()))
    monkeypatch.setattr(devices_tools, "fetch_sensor_device_row", lambda session, request: None)

    with pytest.raises(RuntimeError, match="Unable to get sensor device.") as excinfo:
        devices_tools.get_sensor_device(device_id=str(uuid4()))

    assert isinstance(excinfo.value.__cause__, ValueError)


def test_get_device_health_summary_wraps_invalid_time_range() -> None:
    with pytest.raises(RuntimeError, match="Unable to get device health summary.") as excinfo:
        devices_tools.get_device_health_summary(
            since_ts=datetime(2026, 3, 10, tzinfo=UTC),
            as_of=datetime(2026, 3, 1, tzinfo=UTC),
        )

    assert isinstance(excinfo.value.__cause__, ValueError)
