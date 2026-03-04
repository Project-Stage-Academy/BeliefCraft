import uuid

import pytest
from database.enums import QualityStatus
from database.models import InventoryBalance, Product
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


@pytest.mark.integration
def test_smart_query_inventory_pagination_and_filtering(
    client: TestClient, db_session: Session, seed_base_world: dict
) -> None:
    """
    Validates that the API correctly enforces limit, offset, and SKU filters
    to protect the AI agent's context window.
    """
    loc = seed_base_world["dock"]
    wh = seed_base_world["warehouse"]

    # 1. Arrange: Create 3 distinct products and balances
    products = []
    balances = []

    for i in range(3):
        # We explicitly name SKUs to test alphabetical sorting logic
        prod = Product(id=uuid.uuid4(), sku=f"TEST-SKU-00{i}", name=f"Item {i}", category="Parts")
        bal = InventoryBalance(
            product_id=prod.id,
            location_id=loc.id,
            on_hand=10.0 * (i + 1),  # 10, 20, 30
            reserved=0.0,
            quality_status=QualityStatus.OK,
        )
        products.append(prod)
        balances.append(bal)

    db_session.add_all(products + balances)
    db_session.flush()

    # 2. Act: Test Limit and Offset (Pagination)
    # The default sort is by `available ASC`.
    # Quantities are 10, 20, 30. Skipping 1 (offset=1) should yield the 20-qty item.
    response_page = client.get(
        "/api/v1/smart-query/inventory/current",
        params={"warehouse_id": str(wh.id), "limit": 1, "offset": 1},
    )

    # 3. Assert Pagination Logic
    assert response_page.status_code == 200
    data_page = response_page.json()["data"]

    assert len(data_page) == 1
    assert data_page[0]["sku"] == "TEST-SKU-001"
    assert data_page[0]["on_hand"] == 20.0

    # Verify metadata is accurately tracking the pagination state
    meta = response_page.json()["meta"]
    assert meta["pagination"]["limit"] == 1
    assert meta["pagination"]["offset"] == 1
    assert meta["count"] == 1

    # 4. Act: Test Exact Match Filtering
    response_filter = client.get(
        "/api/v1/smart-query/inventory/current",
        params={"warehouse_id": str(wh.id), "sku": "TEST-SKU-002"},
    )

    # 5. Assert Filtering Logic
    assert response_filter.status_code == 200
    data_filter = response_filter.json()["data"]

    assert len(data_filter) == 1
    assert data_filter[0]["sku"] == "TEST-SKU-002"
    assert data_filter[0]["on_hand"] == 30.0
