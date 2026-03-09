from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from common.schemas.topology import (
    GetWarehouseCapacityUtilizationRequest,
    ListLocationsRequest,
    ListWarehousesRequest,
    TopologyLocationType,
)
from database.enums import DeviceStatus, DeviceType, LocationType, ObservationType
from database.models import Location, Observation, Product, SensorDevice, Warehouse
from environment_api.smart_query_builder.repo.topology import (
    fetch_capacity_utilization_rows,
    fetch_location_rows,
    fetch_warehouse_rows,
)
from sqlalchemy.orm import Session


@pytest.mark.integration
def test_fetch_warehouse_rows_applies_region_and_name_filters(db_session: Session) -> None:
    db_session.add_all(
        [
            Warehouse(name="WH-TOPO-EU-001", region="EU-WEST", tz="UTC"),
            Warehouse(name="WH-TOPO-US-001", region="US-EAST", tz="UTC"),
        ]
    )
    db_session.flush()

    rows = fetch_warehouse_rows(
        db_session,
        ListWarehousesRequest(region="EU-WEST", name_like="TOPO", limit=10, offset=0),
    )

    assert len(rows) == 1
    assert rows[0]["name"] == "WH-TOPO-EU-001"


@pytest.mark.integration
def test_fetch_location_rows_filters_by_warehouse_parent_and_type(db_session: Session) -> None:
    warehouse = Warehouse(name="WH-TOPO-LOC-001", region="EU-WEST", tz="UTC")
    db_session.add(warehouse)
    db_session.flush()

    zone = Location(
        warehouse_id=warehouse.id,
        parent_location_id=None,
        code="WH-TOPO-LOC-001-ZONE-A",
        type=LocationType.VIRTUAL,
        capacity_units=200,
    )
    db_session.add(zone)
    db_session.flush()

    shelf = Location(
        warehouse_id=warehouse.id,
        parent_location_id=zone.id,
        code="WH-TOPO-LOC-001-A-01",
        type=LocationType.SHELF,
        capacity_units=80,
    )
    bin_location = Location(
        warehouse_id=warehouse.id,
        parent_location_id=zone.id,
        code="WH-TOPO-LOC-001-BIN-01",
        type=LocationType.BIN,
        capacity_units=40,
    )
    db_session.add_all([shelf, bin_location])
    db_session.flush()

    rows = fetch_location_rows(
        db_session,
        ListLocationsRequest(
            warehouse_id=warehouse.id,
            parent_location_id=zone.id,
            type=TopologyLocationType.SHELF,
            limit=50,
            offset=0,
        ),
    )

    assert len(rows) == 1
    assert rows[0]["id"] == shelf.id


@pytest.mark.integration
def test_fetch_capacity_utilization_rows_computes_weighted_estimate(db_session: Session) -> None:
    warehouse = Warehouse(name="WH-TOPO-CAP-001", region="EU-WEST", tz="UTC")
    db_session.add(warehouse)
    db_session.flush()

    shelf = Location(
        warehouse_id=warehouse.id,
        parent_location_id=None,
        code="WH-TOPO-CAP-001-SHELF-01",
        type=LocationType.SHELF,
        capacity_units=80,
    )
    db_session.add(shelf)
    db_session.flush()

    product_a = Product(
        sku="SKU-TOPO-A-001",
        name="Topology Product A",
        category="Topology",
        shelf_life_days=365,
    )
    product_b = Product(
        sku="SKU-TOPO-B-001",
        name="Topology Product B",
        category="Topology",
        shelf_life_days=365,
    )
    db_session.add_all([product_a, product_b])
    db_session.flush()

    device = SensorDevice(
        warehouse_id=warehouse.id,
        device_type=DeviceType.CAMERA,
        noise_sigma=0.0,
        missing_rate=0.0,
        bias=0.0,
        status=DeviceStatus.ACTIVE,
    )
    db_session.add(device)
    db_session.flush()

    snapshot_at = datetime.now(UTC)
    db_session.add_all(
        [
            Observation(
                observed_at=snapshot_at - timedelta(hours=2),
                device_id=device.id,
                product_id=product_a.id,
                location_id=shelf.id,
                obs_type=ObservationType.SCAN,
                observed_qty=20.0,
                confidence=0.5,
                is_missing=False,
            ),
            Observation(
                observed_at=snapshot_at - timedelta(hours=1),
                device_id=device.id,
                product_id=product_a.id,
                location_id=shelf.id,
                obs_type=ObservationType.SCAN,
                observed_qty=40.0,
                confidence=1.0,
                is_missing=False,
            ),
            Observation(
                observed_at=snapshot_at - timedelta(minutes=30),
                device_id=device.id,
                product_id=product_b.id,
                location_id=shelf.id,
                obs_type=ObservationType.SCAN,
                observed_qty=10.0,
                confidence=1.0,
                is_missing=False,
            ),
        ]
    )
    db_session.flush()

    rows = fetch_capacity_utilization_rows(
        db_session,
        GetWarehouseCapacityUtilizationRequest(
            warehouse_id=warehouse.id,
            snapshot_at=snapshot_at,
            lookback_hours=24,
            type=TopologyLocationType.SHELF,
        ),
    )

    assert len(rows) == 1
    row = rows[0]

    assert row["location_id"] == shelf.id
    assert row["capacity_units"] == 80
    assert float(row["observed_qty_sum"]) == pytest.approx((20.0 * 0.5 + 40.0 * 1.0) / 1.5 + 10.0)
    assert float(row["confidence_avg"]) == pytest.approx((0.75 + 1.0) / 2)
    assert int(row["obs_count"]) == 3
    assert float(row["utilization_estimate"]) == pytest.approx(
        (((20.0 * 0.5 + 40.0 * 1.0) / 1.5) + 10.0) / 80.0
    )
