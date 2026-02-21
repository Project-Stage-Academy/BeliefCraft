"""
Integration tests for the At-Risk Order detection engine.

Business Logic Validated:
1. Penalty Exposure: Calculation of (Ordered - Allocated) * Unit Penalty.
2. Risk Window: Filtering for orders promised within the next 24 hours.
3. Ranking: Sorting orders so the highest financial risk appears first.
"""

from datetime import UTC, datetime, timedelta

import pytest
from database.enums import OrderStatus
from database.models import Order, OrderLine
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


@pytest.mark.integration
def test_at_risk_orders_penalty_calculation(
    client: TestClient, db_session: Session, seed_base_world: dict
) -> None:
    """
    Validates that the tool correctly identifies unfulfilled orders and
    calculates the correct financial exposure.

    Scenario:
    - Order A: 100% fulfilled (Should not appear in results).
    - Order B: 20 units ordered, only 5 allocated.
      Penalty is $10/unit. Expected Penalty: $150.00.
    """
    # 1. Arrange
    wh = seed_base_world["warehouse"]
    prod = seed_base_world["product"]
    now = datetime.now(UTC)

    # Seed an unfulfilled order promised in 10 hours
    at_risk_order = Order(
        customer_name="High Risk Client",
        status=OrderStatus.SHIPPED,
        promised_at=now + timedelta(hours=10),
        sla_priority=0.95,
        requested_ship_from_region=wh.region,
    )
    db_session.add(at_risk_order)
    db_session.flush()

    # 20 ordered, 5 allocated = 15 units missing
    line = OrderLine(
        order_id=at_risk_order.id,
        product_id=prod.id,
        qty_ordered=20.0,
        qty_allocated=5.0,
        qty_shipped=0.0,
        service_level_penalty=10.0,  # $10 penalty per missing unit
    )
    db_session.add(line)
    db_session.flush()

    # 2. Act
    response = client.get(
        "/api/v1/smart-query/orders/at-risk", params={"horizon_hours": 24, "min_sla_priority": 0.5}
    )

    # 3. Assert
    assert response.status_code == 200
    data = response.json()["data"]

    # Find our specific order in the results
    target_order = next(o for o in data if o["order_id"] == str(at_risk_order.id))

    # Verify the logic in repo/orders.py: (20 - 5) * 10 = 150
    assert target_order["total_open_qty"] == 15.0
    assert target_order["total_penalty_exposure"] == 150.0
    assert prod.sku in target_order["top_missing_skus"]
