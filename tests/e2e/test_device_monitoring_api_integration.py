from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from database.enums import DeviceStatus, DeviceType, ObservationType, QualityStatus
from database.models import InventoryBalance, Observation, Product, SensorDevice
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


def _seed_device_monitoring_records(db_session: Session, seed_base_world: dict) -> dict:
    warehouse = seed_base_world["warehouse"]
    dock = seed_base_world["dock"]
    now = datetime.now(UTC)

    product = Product(
        sku="SKU-DEV-E2E-001",
        name="Device Monitoring Product",
        category="Test",
        shelf_life_days=365,
    )
    db_session.add(product)
    db_session.flush()

    active_device = SensorDevice(
        warehouse_id=warehouse.id,
        device_type=DeviceType.CAMERA,
        status=DeviceStatus.ACTIVE,
        noise_sigma=0.1,
        missing_rate=0.05,
        bias=0.0,
    )
    offline_device = SensorDevice(
        warehouse_id=warehouse.id,
        device_type=DeviceType.SCANNER,
        status=DeviceStatus.OFFLINE,
        noise_sigma=0.1,
        missing_rate=0.05,
        bias=0.0,
    )
    db_session.add_all([active_device, offline_device])
    db_session.flush()

    db_session.add(
        InventoryBalance(
            product_id=product.id,
            location_id=dock.id,
            on_hand=30.0,
            reserved=5.0,
            quality_status=QualityStatus.DAMAGED,
        )
    )
    db_session.add_all(
        [
            Observation(
                observed_at=now - timedelta(minutes=20),
                device_id=active_device.id,
                product_id=product.id,
                location_id=dock.id,
                obs_type=ObservationType.SCAN,
                observed_qty=28.0,
                confidence=0.9,
                is_missing=False,
            ),
            Observation(
                observed_at=now - timedelta(minutes=10),
                device_id=offline_device.id,
                product_id=product.id,
                location_id=dock.id,
                obs_type=ObservationType.SCAN,
                observed_qty=None,
                confidence=0.6,
                is_missing=True,
            ),
            Observation(
                observed_at=now - timedelta(minutes=5),
                device_id=active_device.id,
                product_id=product.id,
                location_id=dock.id,
                obs_type=ObservationType.SCAN,
                observed_qty=29.0,
                confidence=0.95,
                is_missing=False,
            ),
        ]
    )
    db_session.flush()

    return {
        "warehouse": warehouse,
        "active_device": active_device,
        "offline_device": offline_device,
        "product": product,
    }


@pytest.mark.integration
def test_devices_health_and_anomalies_endpoints(
    client: TestClient, db_session: Session, seed_base_world: dict
) -> None:
    seeded = _seed_device_monitoring_records(db_session, seed_base_world)
    warehouse_id = str(seeded["warehouse"].id)

    health_response = client.get(
        "/api/v1/smart-query/devices/health-summary",
        params={"warehouse_id": warehouse_id},
    )
    assert health_response.status_code == 200
    health_payload = health_response.json()
    health_rows = health_payload["data"]
    assert len(health_rows) >= 2
    active_row = next(
        row for row in health_rows if row["device_id"] == str(seeded["active_device"].id)
    )
    assert active_row["obs_count_window"] == 2
    assert active_row["missing_count_window"] == 0

    anomalies_response = client.get(
        "/api/v1/smart-query/devices/anomalies",
        params={"warehouse_id": warehouse_id, "window": 24},
    )
    assert anomalies_response.status_code == 200
    anomalies_payload = anomalies_response.json()
    anomaly_rows = anomalies_payload["data"]
    assert any(
        row["device_id"] == str(seeded["offline_device"].id)
        and "offline_with_observations" in row["anomaly_types"]
        for row in anomaly_rows
    )


@pytest.mark.integration
def test_observed_inventory_snapshot_endpoint_with_dev_mode(
    client: TestClient, db_session: Session, seed_base_world: dict
) -> None:
    seeded = _seed_device_monitoring_records(db_session, seed_base_world)

    response = client.get(
        "/api/v1/smart-query/inventory/observed-snapshot",
        params={"quality_status_in": "damaged", "dev_mode": True},
    )
    assert response.status_code == 200
    payload = response.json()

    assert payload["meta"]["filters"]["quality_status_in"] == ["damaged"]
    rows = payload["data"]
    assert len(rows) >= 1

    row = next(item for item in rows if item["product_id"] == str(seeded["product"].id))
    assert row["quality_status"] == "damaged"
    assert row["observed_qty"] == 29.0
    assert row["on_hand"] == 30.0
    assert row["reserved"] == 5.0
