from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from common.schemas.devices import (
    DeviceStatus as SchemaDeviceStatus,
    DeviceType as SchemaDeviceType,
    GetDeviceAnomaliesRequest,
    GetDeviceHealthSummaryRequest,
    ListSensorDevicesRequest,
)
from database.enums import DeviceStatus, DeviceType, ObservationType
from database.models import Observation, SensorDevice
from environment_api.smart_query_builder.repo.devices import (
    fetch_device_anomaly_candidate_rows,
    fetch_device_health_summary_rows,
    fetch_sensor_device_rows,
)
from sqlalchemy.orm import Session


@pytest.mark.integration
def test_fetch_sensor_device_rows_filters_by_warehouse_and_status(
    db_session: Session, seed_base_world: dict
) -> None:
    warehouse = seed_base_world["warehouse"]

    active_device = SensorDevice(
        warehouse_id=warehouse.id,
        device_type=DeviceType.CAMERA,
        status=DeviceStatus.ACTIVE,
        noise_sigma=0.1,
        missing_rate=0.01,
        bias=0.0,
    )
    offline_device = SensorDevice(
        warehouse_id=warehouse.id,
        device_type=DeviceType.SCANNER,
        status=DeviceStatus.OFFLINE,
        noise_sigma=0.2,
        missing_rate=0.05,
        bias=0.0,
    )
    db_session.add_all([active_device, offline_device])
    db_session.flush()

    rows = fetch_sensor_device_rows(
        db_session,
        ListSensorDevicesRequest(
            warehouse_id=warehouse.id,
            device_type=SchemaDeviceType.CAMERA,
            status=SchemaDeviceStatus.ACTIVE,
        ),
    )

    returned_ids = {row["id"] for row in rows}
    assert active_device.id in returned_ids
    assert offline_device.id not in returned_ids
    assert all(
        str(getattr(row["status"], "value", row["status"])) == "active" for row in rows
    )


@pytest.mark.integration
def test_fetch_device_health_summary_rows_aggregates_observation_window(
    db_session: Session, seed_base_world: dict
) -> None:
    warehouse = seed_base_world["warehouse"]
    dock = seed_base_world["dock"]
    product = seed_base_world["product"]
    now = datetime.now(UTC)

    device = SensorDevice(
        warehouse_id=warehouse.id,
        device_type=DeviceType.CAMERA,
        status=DeviceStatus.ACTIVE,
        noise_sigma=0.05,
        missing_rate=0.05,
        bias=0.0,
    )
    db_session.add(device)
    db_session.flush()

    obs_1 = Observation(
        observed_at=now - timedelta(minutes=20),
        device_id=device.id,
        product_id=product.id,
        location_id=dock.id,
        obs_type=ObservationType.SCAN,
        observed_qty=12.0,
        confidence=0.9,
        is_missing=False,
    )
    obs_2 = Observation(
        observed_at=now - timedelta(minutes=10),
        device_id=device.id,
        product_id=product.id,
        location_id=dock.id,
        obs_type=ObservationType.SCAN,
        observed_qty=None,
        confidence=0.2,
        is_missing=True,
    )
    db_session.add_all([obs_1, obs_2])
    db_session.flush()

    rows = fetch_device_health_summary_rows(
        db_session,
        GetDeviceHealthSummaryRequest(
            warehouse_id=warehouse.id,
            since_ts=now - timedelta(hours=1),
            as_of=now,
        ),
    )

    row = next(r for r in rows if r["device_id"] == device.id)
    assert row["last_seen_at"] == obs_2.observed_at
    assert int(row["obs_count_window"]) == 2
    assert int(row["missing_count_window"]) == 1
    assert int(row["observed_null_count"]) == 1
    assert float(row["avg_confidence"]) == pytest.approx(0.55)


@pytest.mark.integration
def test_fetch_device_anomaly_candidate_rows_respects_window(
    db_session: Session, seed_base_world: dict
) -> None:
    warehouse = seed_base_world["warehouse"]
    dock = seed_base_world["dock"]
    product = seed_base_world["product"]
    now = datetime.now(UTC)

    offline_device = SensorDevice(
        warehouse_id=warehouse.id,
        device_type=DeviceType.CAMERA,
        status=DeviceStatus.OFFLINE,
        noise_sigma=0.1,
        missing_rate=0.1,
        bias=0.0,
    )
    active_device = SensorDevice(
        warehouse_id=warehouse.id,
        device_type=DeviceType.SCANNER,
        status=DeviceStatus.ACTIVE,
        noise_sigma=0.1,
        missing_rate=0.1,
        bias=0.0,
    )
    db_session.add_all([offline_device, active_device])
    db_session.flush()

    db_session.add_all(
        [
            Observation(
                observed_at=now - timedelta(minutes=20),
                device_id=offline_device.id,
                product_id=product.id,
                location_id=dock.id,
                obs_type=ObservationType.SCAN,
                observed_qty=None,
                confidence=0.7,
                is_missing=True,
            ),
            Observation(
                observed_at=now - timedelta(hours=2),
                device_id=offline_device.id,
                product_id=product.id,
                location_id=dock.id,
                obs_type=ObservationType.SCAN,
                observed_qty=8.0,
                confidence=0.8,
                is_missing=False,
            ),
        ]
    )
    db_session.flush()

    rows = fetch_device_anomaly_candidate_rows(
        db_session,
        GetDeviceAnomaliesRequest(warehouse_id=warehouse.id, window=1),
    )

    offline_row = next(r for r in rows if r["device_id"] == offline_device.id)
    active_row = next(r for r in rows if r["device_id"] == active_device.id)

    assert int(offline_row["obs_count_window"]) == 1
    assert int(offline_row["missing_count_window"]) == 1
    assert float(offline_row["observed_missing_rate"]) == 1.0

    assert int(active_row["obs_count_window"]) == 0
    assert int(active_row["missing_count_window"]) == 0
    assert active_row["observed_missing_rate"] is None
