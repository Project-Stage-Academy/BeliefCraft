from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from common.schemas.procurement import (
    ListPoLinesRequest,
    ListPurchaseOrdersRequest,
    ListSuppliersRequest,
)
from common.schemas.procurement import POStatus as SchemaPOStatus
from common.schemas.procurement import (
    ProcurementGroupBy,
    ProcurementPipelineSummaryRequest,
)
from database.enums import POStatus as DbPOStatus
from database.models import POLine, PurchaseOrder, Supplier
from environment_api.smart_query_builder.repo.procurement import (
    fetch_po_line_rows,
    fetch_procurement_pipeline_summary_rows,
    fetch_purchase_order_rows,
    fetch_supplier_rows,
)
from sqlalchemy.orm import Session


def _seed_purchase_orders(db_session: Session, seed_base_world: dict) -> dict:
    supplier = seed_base_world["supplier"]
    warehouse = seed_base_world["warehouse"]
    product = seed_base_world["product"]
    now = datetime.now(UTC)

    submitted_po = PurchaseOrder(
        supplier_id=supplier.id,
        destination_warehouse_id=warehouse.id,
        status=DbPOStatus.SUBMITTED,
        expected_at=now + timedelta(days=4),
    )
    partial_po = PurchaseOrder(
        supplier_id=supplier.id,
        destination_warehouse_id=warehouse.id,
        status=DbPOStatus.PARTIAL,
        expected_at=now + timedelta(days=2),
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
def test_fetch_supplier_rows_applies_filters(db_session: Session) -> None:
    db_session.add_all(
        [
            Supplier(name="AAA EU", reliability_score=0.95, region="EU-WEST"),
            Supplier(name="BBB EU LOW", reliability_score=0.40, region="EU-WEST"),
            Supplier(name="CCC US", reliability_score=0.97, region="US-EAST"),
        ]
    )
    db_session.flush()

    request = ListSuppliersRequest(region="EU-WEST", reliability_min=0.8, name_like="AA")
    rows = fetch_supplier_rows(db_session, request)

    assert len(rows) == 1
    assert rows[0]["name"] == "AAA EU"
    assert rows[0]["region"] == "EU-WEST"


@pytest.mark.integration
def test_fetch_purchase_order_rows_filters_status_and_includes_names(
    db_session: Session, seed_base_world: dict
) -> None:
    seeded = _seed_purchase_orders(db_session, seed_base_world)

    rows = fetch_purchase_order_rows(
        db_session,
        ListPurchaseOrdersRequest(
            supplier_id=seeded["supplier"].id,
            status_in=[SchemaPOStatus.SUBMITTED],
            include_names=True,
        ),
    )

    assert len(rows) == 1
    row = rows[0]
    status_value = getattr(row["status"], "value", row["status"])
    assert row["id"] == seeded["submitted_po"].id
    assert str(status_value).lower() == "submitted"
    assert row["supplier_name"] == seeded["supplier"].name
    assert row["warehouse_name"] == seeded["warehouse"].name


@pytest.mark.integration
def test_fetch_po_line_rows_computes_remaining_and_product_fields(
    db_session: Session, seed_base_world: dict
) -> None:
    seeded = _seed_purchase_orders(db_session, seed_base_world)

    rows = fetch_po_line_rows(
        db_session,
        ListPoLinesRequest(
            purchase_order_id=seeded["submitted_po"].id,
            include_product_fields=True,
        ),
    )

    assert len(rows) == 1
    row = rows[0]
    assert row["purchase_order_id"] == seeded["submitted_po"].id
    assert float(row["qty_ordered"]) == 10.0
    assert float(row["qty_received"]) == 2.0
    assert float(row["remaining_qty"]) == 8.0
    assert row["sku"] == seeded["product"].sku
    assert row["product_name"] == seeded["product"].name


@pytest.mark.integration
def test_fetch_procurement_pipeline_summary_rows_aggregates_by_warehouse_supplier(
    db_session: Session, seed_base_world: dict
) -> None:
    seeded = _seed_purchase_orders(db_session, seed_base_world)

    rows = fetch_procurement_pipeline_summary_rows(
        db_session,
        ProcurementPipelineSummaryRequest(
            supplier_id=seeded["supplier"].id,
            group_by=ProcurementGroupBy.warehouse_supplier,
            include_names=True,
        ),
    )

    assert len(rows) == 1
    row = rows[0]
    assert row["supplier_id"] == seeded["supplier"].id
    assert row["destination_warehouse_id"] == seeded["warehouse"].id
    assert row["po_count"] == 2
    assert float(row["total_qty_ordered"]) == 15.0
    assert float(row["total_qty_received"]) == 4.0
    assert float(row["total_qty_remaining"]) == 11.0
    assert row["supplier_name"] == seeded["supplier"].name
    assert row["warehouse_name"] == seeded["warehouse"].name
