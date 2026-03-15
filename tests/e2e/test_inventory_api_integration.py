"""Integration tests for Smart Query inventory audit endpoints."""

from datetime import UTC, datetime

import pytest
from database.enums import MoveType
from database.models import InventoryMove
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


@pytest.mark.integration
def test_list_inventory_moves_endpoint(
    client: TestClient, db_session: Session, seed_base_world: dict
) -> None:
    warehouse = seed_base_world["warehouse"]
    dock = seed_base_world["dock"]
    product = seed_base_world["product"]

    move = InventoryMove(
        product_id=product.id,
        from_location_id=dock.id,
        to_location_id=None,
        move_type=MoveType.ADJUSTMENT,
        qty=5.0,
        occurred_at=datetime.now(UTC),
        reason_code="cycle_count_gain",
    )
    db_session.add(move)
    db_session.flush()

    response = client.get(
        "/api/v1/smart-query/inventory/moves",
        params={"warehouse_id": str(warehouse.id), "product_id": str(product.id)},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["meta"]["count"] == 1
    assert payload["data"]["moves"][0]["reason_code"] == "cycle_count_gain"
