from __future__ import annotations

from datetime import UTC, datetime

from database.enums import MoveType
from database.models import InventoryMove


def test_inventory_moves_accepts_sku_like_product_id(
    client, db_session, seed_base_world
) -> None:
    product = seed_base_world["product"]
    dock = seed_base_world["dock"]

    move = InventoryMove(
        product_id=product.id,
        from_location_id=None,
        to_location_id=dock.id,
        move_type=MoveType.INBOUND,
        qty=12.0,
        occurred_at=datetime.now(tz=UTC),
        reason_code=None,
    )
    db_session.add(move)
    db_session.commit()

    response = client.get(
        "/api/v1/smart-query/inventory/moves",
        params={"product_id": product.sku, "limit": 50},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["moves"]
    assert body["data"]["moves"][0]["product_id"] == str(product.id)


def test_inventory_adjustments_summary_accepts_sku_like_product_id(
    client, db_session, seed_base_world
) -> None:
    product = seed_base_world["product"]
    dock = seed_base_world["dock"]

    adjustment = InventoryMove(
        product_id=product.id,
        from_location_id=dock.id,
        to_location_id=dock.id,
        move_type=MoveType.ADJUSTMENT,
        qty=3.0,
        occurred_at=datetime.now(tz=UTC),
        reason_code="cycle_count",
        reported_qty=8.0,
        actual_qty=5.0,
    )
    db_session.add(adjustment)
    db_session.commit()

    response = client.get(
        "/api/v1/smart-query/inventory/adjustments-summary",
        params={"product_id": product.sku},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["count"] == 1
    assert body["data"]["total_qty"] == 3.0
    assert body["data"]["by_reason"][0]["reason_code"] == "cycle_count"
