"""
Integration tests for Smart Query topology endpoints.
"""

from datetime import UTC, datetime, timedelta

import pytest
from database.enums import DeviceStatus, DeviceType, LocationType, ObservationType
from database.models import Location, Observation, Product, SensorDevice, Warehouse
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


def _seed_topology_records(db_session: Session, seed_base_world: dict) -> dict:
    product_a = seed_base_world["product"]

    warehouse = Warehouse(name="WH-TOPO-E2E-001", region="EU-WEST", tz="UTC")
    db_session.add(warehouse)
    db_session.flush()

    zone = Location(
        warehouse_id=warehouse.id,
        parent_location_id=None,
        code="WH-TOPO-E2E-001-ZONE-A",
        type=LocationType.VIRTUAL,
        capacity_units=120,
    )
    db_session.add(zone)
    db_session.flush()

    shelf = Location(
        warehouse_id=warehouse.id,
        parent_location_id=zone.id,
        code="WH-TOPO-E2E-001-A-01",
        type=LocationType.SHELF,
        capacity_units=80,
    )
    bin_location = Location(
        warehouse_id=warehouse.id,
        parent_location_id=shelf.id,
        code="WH-TOPO-E2E-001-A-01-BIN-01",
        type=LocationType.BIN,
        capacity_units=40,
    )
    db_session.add_all([shelf, bin_location])
    db_session.flush()

    product_b = Product(
        sku="SKU-TOPO-E2E-B-001",
        name="Topology E2E Product B",
        category="Topology",
        shelf_life_days=365,
    )
    db_session.add(product_b)
    db_session.flush()

    sensor = SensorDevice(
        warehouse_id=warehouse.id,
        device_type=DeviceType.CAMERA,
        noise_sigma=0.0,
        missing_rate=0.0,
        bias=0.0,
        status=DeviceStatus.ACTIVE,
    )
    db_session.add(sensor)
    db_session.flush()

    snapshot_at = datetime.now(UTC)
    db_session.add_all(
        [
            Observation(
                observed_at=snapshot_at - timedelta(hours=2),
                device_id=sensor.id,
                product_id=product_a.id,
                location_id=shelf.id,
                obs_type=ObservationType.SCAN,
                observed_qty=20.0,
                confidence=0.5,
                is_missing=False,
            ),
            Observation(
                observed_at=snapshot_at - timedelta(hours=1),
                device_id=sensor.id,
                product_id=product_a.id,
                location_id=shelf.id,
                obs_type=ObservationType.SCAN,
                observed_qty=40.0,
                confidence=1.0,
                is_missing=False,
            ),
            Observation(
                observed_at=snapshot_at - timedelta(minutes=30),
                device_id=sensor.id,
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

    return {
        "warehouse": warehouse,
        "zone": zone,
        "shelf": shelf,
        "bin": bin_location,
        "snapshot_at": snapshot_at,
    }


@pytest.mark.integration
def test_topology_warehouses_endpoint_filters_by_region_and_name(
    client: TestClient, db_session: Session, seed_base_world: dict
) -> None:
    seeded = _seed_topology_records(db_session, seed_base_world)

    response = client.get(
        "/api/v1/smart-query/topology/warehouses",
        params={"region": "EU-WEST", "name_like": "TOPO-E2E"},
    )

    assert response.status_code == 200
    payload = response.json()

    assert payload["meta"]["filters"]["region"] == "EU-WEST"
    ids = {row["id"] for row in payload["data"]["warehouses"]}
    assert str(seeded["warehouse"].id) in ids


@pytest.mark.integration
def test_topology_get_warehouse_endpoint_returns_full_record(
    client: TestClient, db_session: Session, seed_base_world: dict
) -> None:
    seeded = _seed_topology_records(db_session, seed_base_world)

    response = client.get(f"/api/v1/smart-query/topology/warehouses/{seeded['warehouse'].id}")

    assert response.status_code == 200
    payload = response.json()

    assert payload["data"]["warehouse"]["id"] == str(seeded["warehouse"].id)
    assert payload["data"]["warehouse"]["name"] == seeded["warehouse"].name


@pytest.mark.integration
def test_topology_locations_endpoint_filters_by_type_and_parent(
    client: TestClient, db_session: Session, seed_base_world: dict
) -> None:
    seeded = _seed_topology_records(db_session, seed_base_world)

    response = client.get(
        "/api/v1/smart-query/topology/locations",
        params=[
            ("warehouse_id", str(seeded["warehouse"].id)),
            ("type", "shelf"),
            ("parent_location_id", str(seeded["zone"].id)),
        ],
    )

    assert response.status_code == 200
    payload = response.json()

    assert payload["meta"]["count"] == 1
    row = payload["data"]["locations"][0]
    assert row["id"] == str(seeded["shelf"].id)
    assert row["type"] == "shelf"


@pytest.mark.integration
def test_topology_get_location_endpoint_returns_full_record(
    client: TestClient, db_session: Session, seed_base_world: dict
) -> None:
    seeded = _seed_topology_records(db_session, seed_base_world)

    response = client.get(f"/api/v1/smart-query/topology/locations/{seeded['shelf'].id}")

    assert response.status_code == 200
    payload = response.json()

    assert payload["data"]["location"]["id"] == str(seeded["shelf"].id)
    assert payload["data"]["location"]["parent_location_id"] == str(seeded["zone"].id)


@pytest.mark.integration
def test_topology_locations_tree_endpoint_returns_nested_structure(
    client: TestClient, db_session: Session, seed_base_world: dict
) -> None:
    seeded = _seed_topology_records(db_session, seed_base_world)

    response = client.get(
        f"/api/v1/smart-query/topology/warehouses/{seeded['warehouse'].id}/locations-tree"
    )

    assert response.status_code == 200
    payload = response.json()

    assert payload["data"]["warehouse_id"] == str(seeded["warehouse"].id)
    assert payload["data"]["node_count"] == 3

    roots = payload["data"]["roots"]
    zone = next(node for node in roots if node["id"] == str(seeded["zone"].id))
    shelf = next(node for node in zone["children"] if node["id"] == str(seeded["shelf"].id))
    assert shelf["children"][0]["id"] == str(seeded["bin"].id)


@pytest.mark.integration
def test_topology_capacity_utilization_endpoint_uses_observations_snapshot(
    client: TestClient, db_session: Session, seed_base_world: dict
) -> None:
    seeded = _seed_topology_records(db_session, seed_base_world)

    response = client.get(
        f"/api/v1/smart-query/topology/warehouses/{seeded['warehouse'].id}/capacity-utilization",
        params={
            "snapshot_at": seeded["snapshot_at"].isoformat(),
            "lookback_hours": 24,
            "type": "shelf",
        },
    )

    assert response.status_code == 200
    payload = response.json()

    assert payload["meta"]["filters"]["type"] == "shelf"
    assert payload["data"]["location_count"] == 1

    row = payload["data"]["rows"][0]
    assert row["location_id"] == str(seeded["shelf"].id)
    assert row["capacity_units"] == 80
    assert row["observed_qty_sum"] == pytest.approx((20.0 * 0.5 + 40.0 * 1.0) / 1.5 + 10.0)
    assert row["confidence_avg"] == pytest.approx((0.75 + 1.0) / 2)
    assert row["obs_count"] == 3
    assert row["utilization_estimate"] == pytest.approx(
        (((20.0 * 0.5 + 40.0 * 1.0) / 1.5) + 10.0) / 80.0
    )
