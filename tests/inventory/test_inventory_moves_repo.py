from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from common.schemas.inventory import (
    GetInventoryAdjustmentsSummaryRequest,
    GetInventoryMoveAuditTraceRequest,
    GetInventoryMoveRequest,
    ListInventoryMovesRequest,
)
from database.enums import MoveType
from database.inventory import InventoryMove
from sqlalchemy.orm import Session

from environment_api.smart_query_builder.repo.inventory_moves import (
    fetch_inventory_adjustments_summary,
    fetch_inventory_move_audit_trace_rows,
    fetch_inventory_move_row,
    fetch_inventory_move_rows,
)


def _seed_inventory_moves(db_session: Session, seed_base_world: dict) -> dict:
    warehouse = seed_base_world["warehouse"]
    dock = seed_base_world["dock"]
    product = seed_base_world["product"]
    now = datetime.now(UTC)

    move_transfer = InventoryMove(
        product_id=product.id,
        from_location_id=dock.id,
        to_location_id=None,
        move_type=MoveType.TRANSFER,
        qty=10.0,
        occurred_at=now - timedelta(hours=2),
        reason_code=None,
    )
    move_adjustment_good = InventoryMove(
        product_id=product.id,
        from_location_id=None,
        to_location_id=dock.id,
        move_type=MoveType.ADJUSTMENT,
        qty=3.0,
        occurred_at=now - timedelta(hours=1),
        reason_code="cycle_count_gain",
    )
    move_adjustment_bad = InventoryMove(
        product_id=product.id,
        from_location_id=None,
        to_location_id=dock.id,
        move_type=MoveType.ADJUSTMENT,
        qty=2.0,
        occurred_at=now,
        reason_code="cycle_count_loss",
    )

    db_session.add_all([move_transfer, move_adjustment_good, move_adjustment_bad])
    db_session.flush()

    return {
        "warehouse": warehouse,
        "dock": dock,
        "product": product,
        "move_transfer": move_transfer,
        "move_adjustment_good": move_adjustment_good,
        "move_adjustment_bad": move_adjustment_bad,
    }


@pytest.mark.integration
def test_fetch_inventory_move_rows_applies_filters(db_session: Session, seed_base_world: dict) -> None:
    seeded = _seed_inventory_moves(db_session, seed_base_world)

    request = ListInventoryMovesRequest(
        warehouse_id=str(seeded["warehouse"].id),
        product_id=str(seeded["product"].id),
        move_type=MoveType.ADJUSTMENT.value,
    )
    rows = fetch_inventory_move_rows(db_session, request)

    assert len(rows) == 2
    move_types = {row["move_type"] for row in rows}
    assert move_types == {MoveType.ADJUSTMENT.value}


@pytest.mark.integration
def test_fetch_inventory_move_row_returns_single_move(db_session: Session, seed_base_world: dict) -> None:
    seeded = _seed_inventory_moves(db_session, seed_base_world)

    request = GetInventoryMoveRequest(move_id=str(seeded["move_transfer"].id))
    row = fetch_inventory_move_row(db_session, request)

    assert row is not None
    assert row["id"] == seeded["move_transfer"].id
    assert float(row["qty"]) == 10.0


@pytest.mark.integration
def test_fetch_inventory_adjustments_summary_aggregates_by_reason(
    db_session: Session, seed_base_world: dict
) -> None:
    seeded = _seed_inventory_moves(db_session, seed_base_world)

    request = GetInventoryAdjustmentsSummaryRequest(
        warehouse_id=str(seeded["warehouse"].id),
        product_id=str(seeded["product"].id),
    )
    summary_row, breakdown_rows = fetch_inventory_adjustments_summary(db_session, request)

    assert int(summary_row["count"]) == 2
    assert float(summary_row["total_qty"]) == 5.0

    breakdown = {row["reason_code"]: float(row["total_qty"]) for row in breakdown_rows}
    assert breakdown["cycle_count_gain"] == 3.0
    assert breakdown["cycle_count_loss"] == 2.0

