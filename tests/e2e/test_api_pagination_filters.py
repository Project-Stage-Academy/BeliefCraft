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
