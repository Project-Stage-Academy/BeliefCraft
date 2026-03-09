from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from common.schemas.observed_inventory import (
    GetObservedInventorySnapshotRequest,
    ObservedInventoryQualityStatus,
)
from database.enums import DeviceStatus, DeviceType, ObservationType, QualityStatus
from database.models import InventoryBalance, Observation, Product, SensorDevice
from environment_api.smart_query_builder.repo.observed_inventory import (
    _build_latest_observations_subquery,
    _build_snapshot_stmt,
    fetch_observed_inventory_snapshot_rows,
)
from sqlalchemy.orm import Session


def test_build_latest_observations_subquery_has_expected_projection() -> None:
    subquery = _build_latest_observations_subquery(Observation.__table__)

    assert subquery.name == "latest_observations"
    assert {"product_id", "location_id", "observed_qty", "confidence", "device_id", "rn"}.issubset(
        set(subquery.c.keys())
    )


def test_build_snapshot_stmt_adds_quality_filter() -> None:
    stmt = _build_snapshot_stmt(
        {
            "observations": Observation.__table__,
            "inventory_balances": InventoryBalance.__table__,
        },
        GetObservedInventorySnapshotRequest(quality_status_in=[ObservedInventoryQualityStatus.OK]),
    )

    sql = str(stmt).lower()
    assert "quality_status" in sql
    assert " in " in sql


@pytest.mark.integration
def test_fetch_observed_inventory_snapshot_rows_uses_latest_observation(
    db_session: Session, seed_base_world: dict
) -> None:
    warehouse = seed_base_world["warehouse"]
    dock = seed_base_world["dock"]
    now = datetime.now(UTC)

    product = Product(
        sku="SKU-OBS-SNAP-001",
        name="Observed Snapshot Product",
        category="Test",
        shelf_life_days=365,
    )
    db_session.add(product)
    db_session.flush()

    device = SensorDevice(
        warehouse_id=warehouse.id,
        device_type=DeviceType.CAMERA,
        status=DeviceStatus.ACTIVE,
        noise_sigma=0.0,
        missing_rate=0.0,
        bias=0.0,
    )
    db_session.add(device)
    db_session.flush()

    db_session.add(
        InventoryBalance(
            product_id=product.id,
            location_id=dock.id,
            on_hand=25.0,
            reserved=2.0,
            quality_status=QualityStatus.DAMAGED,
        )
    )
    db_session.flush()

    db_session.add_all(
        [
            Observation(
                observed_at=now - timedelta(minutes=30),
                device_id=device.id,
                product_id=product.id,
                location_id=dock.id,
                obs_type=ObservationType.SCAN,
                observed_qty=20.0,
                confidence=0.6,
                is_missing=False,
            ),
            Observation(
                observed_at=now - timedelta(minutes=5),
                device_id=device.id,
                product_id=product.id,
                location_id=dock.id,
                obs_type=ObservationType.SCAN,
                observed_qty=22.0,
                confidence=0.9,
                is_missing=False,
            ),
        ]
    )
    db_session.flush()

    rows = fetch_observed_inventory_snapshot_rows(
        db_session,
        GetObservedInventorySnapshotRequest(
            quality_status_in=[ObservedInventoryQualityStatus.DAMAGED],
            dev_mode=True,
        ),
    )

    assert len(rows) == 1
    row = rows[0]
    assert row["product_id"] == product.id
    assert row["location_id"] == dock.id
    assert float(row["observed_qty"]) == 22.0
    assert float(row["confidence"]) == 0.9
    assert row["device_id"] == device.id
    assert str(getattr(row["quality_status"], "value", row["quality_status"])) == "damaged"
    assert float(row["on_hand"]) == 25.0
    assert float(row["reserved"]) == 2.0


@pytest.mark.integration
def test_fetch_observed_inventory_snapshot_rows_applies_quality_filter(
    db_session: Session, seed_base_world: dict
) -> None:
    warehouse = seed_base_world["warehouse"]
    dock = seed_base_world["dock"]
    product = Product(
        sku="SKU-OBS-SNAP-002",
        name="Observed Snapshot Product 2",
        category="Test",
        shelf_life_days=365,
    )
    db_session.add(product)
    db_session.flush()

    device = SensorDevice(
        warehouse_id=warehouse.id,
        device_type=DeviceType.SCANNER,
        status=DeviceStatus.ACTIVE,
    )
    db_session.add(device)
    db_session.flush()

    db_session.add(
        InventoryBalance(
            product_id=product.id,
            location_id=dock.id,
            on_hand=15.0,
            reserved=0.0,
            quality_status=QualityStatus.OK,
        )
    )
    db_session.add(
        Observation(
            observed_at=datetime.now(UTC),
            device_id=device.id,
            product_id=product.id,
            location_id=dock.id,
            obs_type=ObservationType.SCAN,
            observed_qty=14.0,
            confidence=0.8,
            is_missing=False,
        )
    )
    db_session.flush()

    rows = fetch_observed_inventory_snapshot_rows(
        db_session,
        GetObservedInventorySnapshotRequest(
            quality_status_in=[ObservedInventoryQualityStatus.EXPIRED]
        ),
    )

    assert rows == []
