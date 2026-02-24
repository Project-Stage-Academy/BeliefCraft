"""
Integration tests for Smart Query procurement endpoints.
"""

from datetime import UTC, datetime, timedelta

import pytest
from database.enums import POStatus
from database.models import POLine, PurchaseOrder
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


def _seed_procurement_records(db_session: Session, seed_base_world: dict) -> dict:
    supplier = seed_base_world["supplier"]
    warehouse = seed_base_world["warehouse"]
    product = seed_base_world["product"]
    now = datetime.now(UTC)

    submitted_po = PurchaseOrder(
        supplier_id=supplier.id,
        destination_warehouse_id=warehouse.id,
        status=POStatus.SUBMITTED,
        expected_at=now + timedelta(days=3),
    )
    partial_po = PurchaseOrder(
        supplier_id=supplier.id,
        destination_warehouse_id=warehouse.id,
        status=POStatus.PARTIAL,
        expected_at=now + timedelta(days=1),
    )
    db_session.add_all([submitted_po, partial_po])
    db_session.flush()

    db_session.add_all(
        [
            POLine(
                purchase_order_id=submitted_po.id,
                product_id=product.id,
                qty_ordered=10.0,
                qty_received=2.0,
            ),
            POLine(
                purchase_order_id=partial_po.id,
                product_id=product.id,
                qty_ordered=5.0,
                qty_received=2.0,
            ),
        ]
    )
    db_session.flush()

    return {
        "supplier": supplier,
        "warehouse": warehouse,
        "product": product,
        "submitted_po": submitted_po,
        "partial_po": partial_po,
    }


@pytest.mark.integration
def test_procurement_suppliers_endpoint_filters_by_region(
    client: TestClient, seed_base_world: dict
) -> None:
    supplier = seed_base_world["supplier"]

    response = client.get(
        "/api/v1/smart-query/procurement/suppliers",
        params={"region": supplier.region},
    )

    assert response.status_code == 200
    payload = response.json()

    assert payload["meta"]["filters"]["region"] == supplier.region
    ids = {row["id"] for row in payload["data"]["suppliers"]}
    assert str(supplier.id) in ids


@pytest.mark.integration
def test_procurement_purchase_orders_endpoint_filters_status_and_returns_names(
    client: TestClient, db_session: Session, seed_base_world: dict
) -> None:
    seeded = _seed_procurement_records(db_session, seed_base_world)

    response = client.get(
        "/api/v1/smart-query/procurement/purchase-orders",
        params=[
            ("supplier_id", str(seeded["supplier"].id)),
            ("status_in", "submitted"),
            ("include_names", "true"),
        ],
    )

    assert response.status_code == 200
    payload = response.json()
    rows = payload["data"]["purchase_orders"]

    assert payload["meta"]["count"] == 1
    assert rows[0]["id"] == str(seeded["submitted_po"].id)
    assert rows[0]["supplier_name"] == seeded["supplier"].name
    assert rows[0]["warehouse_name"] == seeded["warehouse"].name
    assert rows[0]["status"] == "submitted"


@pytest.mark.integration
def test_procurement_pipeline_summary_endpoint_aggregates_po_lines(
    client: TestClient, db_session: Session, seed_base_world: dict
) -> None:
    seeded = _seed_procurement_records(db_session, seed_base_world)

    response = client.get(
        "/api/v1/smart-query/procurement/pipeline-summary",
        params=[
            ("supplier_id", str(seeded["supplier"].id)),
            ("group_by", "warehouse_supplier"),
            ("include_names", "true"),
        ],
    )

    assert response.status_code == 200
    payload = response.json()
    rows = payload["data"]["rows"]

    assert payload["meta"]["count"] == 1
    row = rows[0]
    assert row["supplier_id"] == str(seeded["supplier"].id)
    assert row["destination_warehouse_id"] == str(seeded["warehouse"].id)
    assert row["supplier_name"] == seeded["supplier"].name
    assert row["warehouse_name"] == seeded["warehouse"].name
    assert row["po_count"] == 2
    assert row["total_qty_ordered"] == 15.0
    assert row["total_qty_received"] == 4.0
    assert row["total_qty_remaining"] == 11.0
