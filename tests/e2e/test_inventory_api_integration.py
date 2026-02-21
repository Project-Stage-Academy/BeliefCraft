"""
Integration tests for the Smart Query Builder Inventory endpoints.
"""

import pytest
from database.enums import QualityStatus
from database.models import InventoryBalance
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


@pytest.mark.integration
def test_get_current_inventory_endpoint(
    client: TestClient, db_session: Session, seed_base_world: dict
) -> None:
    """
    Verifies the /inventory/current endpoint correctly aggregates and calculates
    available stock using the pre-seeded infrastructure from seed_base_world.

    Test Setup:
    1. Uses seeded Warehouse, Dock, and Product from seed_base_world.
    2. Seeds an InventoryBalance of 50 units with 15 reserved.

    Assertions:
    1. The API returns a 200 OK status.
    2. The 'available' calculated field correctly resolves to 35.0 (50 - 15).
    """
    # 1. Retrieve seeded entities from the fixture
    warehouse = seed_base_world["warehouse"]
    dock = seed_base_world["dock"]
    product = seed_base_world["product"]

    # 2. Seed only the transactional data specific to this test
    balance = InventoryBalance(
        location_id=dock.id,
        product_id=product.id,
        on_hand=50.0,
        reserved=15.0,
        quality_status=QualityStatus.OK,
    )
    db_session.add(balance)
    db_session.flush()

    # 3. Execute API call
    response = client.get(
        "/api/v1/smart-query/inventory/current",
        params={"warehouse_id": str(warehouse.id), "include_reserved": True},
    )

    # 4. Assertions
    assert response.status_code == 200
    payload = response.json()

    assert payload["meta"]["count"] == 1

    data = payload["data"][0]
    # SKU comes from the WorldBuilder's deterministic generation (seed=42)
    assert data["sku"] == product.sku
    assert data["on_hand"] == 50.0
    assert data["reserved"] == 15.0
    assert data["available"] == 35.0
