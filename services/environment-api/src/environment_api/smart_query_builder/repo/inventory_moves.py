from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from common.schemas.inventory import (
    GetInventoryAdjustmentsSummaryRequest,
    GetInventoryMoveAuditTraceRequest,
    GetInventoryMoveRequest,
    ListInventoryMovesRequest,
)
from database.inventory import InventoryMove, Location, Product
from database.logistics import Warehouse
from database.observations import Observation
from sqlalchemy import func, or_, select
from sqlalchemy.engine import RowMapping
from sqlalchemy.orm import Session
from sqlalchemy.sql.selectable import FromClause


def _load_tables(session: Session) -> dict[str, FromClause]:
    if session.get_bind() is None:
        raise RuntimeError("Database session is not bound.")

    return {
        "inventory_moves": InventoryMove.__table__,
        "products": Product.__table__,
        "locations": Location.__table__,
        "warehouses": Warehouse.__table__,
        "observations": Observation.__table__,
    }


def _build_warehouse_filter_clause(
    warehouse_id: str | None,
    locations: FromClause,
    moves: FromClause,
) -> tuple[FromClause, list]:
    """
    Build join/where fragments to support filtering moves by warehouse via locations.
    """
    conditions: list = []
    from_clause: FromClause = moves

    if warehouse_id is not None:
        loc_from = locations.alias("loc_from")
        loc_to = locations.alias("loc_to")

        from_clause = (
            moves.outerjoin(loc_from, loc_from.c.id == moves.c.from_location_id)
            .outerjoin(loc_to, loc_to.c.id == moves.c.to_location_id)
        )

        conditions.append(
            or_(
                loc_from.c.warehouse_id == warehouse_id,
                loc_to.c.warehouse_id == warehouse_id,
            )
        )

    return from_clause, conditions


def fetch_inventory_move_rows(
    session: Session,
    request: ListInventoryMovesRequest,
) -> Sequence[RowMapping]:
    tables = _load_tables(session)
    moves = tables["inventory_moves"]
    locations = tables["locations"]

    from_clause, conditions = _build_warehouse_filter_clause(
        request.warehouse_id,
        locations,
        moves,
    )

    stmt = (
        select(
            moves.c.id.label("id"),
            moves.c.product_id.label("product_id"),
            moves.c.from_location_id.label("from_location_id"),
            moves.c.to_location_id.label("to_location_id"),
            moves.c.move_type.label("move_type"),
            moves.c.qty.label("qty"),
            moves.c.occurred_at.label("occurred_at"),
            moves.c.reason_code.label("reason_code"),
            moves.c.reported_qty.label("reported_qty"),
            moves.c.actual_qty.label("actual_qty"),
        )
        .select_from(from_clause)
        .order_by(moves.c.occurred_at.desc(), moves.c.id.asc())
        .limit(request.limit)
        .offset(request.offset)
    )

    if request.product_id:
        conditions.append(moves.c.product_id == request.product_id)
    if request.move_type:
        conditions.append(moves.c.move_type == request.move_type)
    if request.from_ts:
        conditions.append(moves.c.occurred_at >= request.from_ts)
    if request.to_ts:
        conditions.append(moves.c.occurred_at <= request.to_ts)

    if conditions:
        stmt = stmt.where(*conditions)

    return session.execute(stmt).mappings().all()


def fetch_inventory_move_row(
    session: Session,
    request: GetInventoryMoveRequest,
) -> RowMapping | None:
    tables = _load_tables(session)
    moves = tables["inventory_moves"]

    stmt = (
        select(
            moves.c.id.label("id"),
            moves.c.product_id.label("product_id"),
            moves.c.from_location_id.label("from_location_id"),
            moves.c.to_location_id.label("to_location_id"),
            moves.c.move_type.label("move_type"),
            moves.c.qty.label("qty"),
            moves.c.occurred_at.label("occurred_at"),
            moves.c.reason_code.label("reason_code"),
            moves.c.reported_qty.label("reported_qty"),
            moves.c.actual_qty.label("actual_qty"),
        )
        .select_from(moves)
        .where(moves.c.id == request.move_id)
        .limit(1)
    )

    return session.execute(stmt).mappings().one_or_none()


def fetch_inventory_move_audit_trace_rows(
    session: Session,
    request: GetInventoryMoveAuditTraceRequest,
) -> tuple[RowMapping | None, Sequence[RowMapping]]:
    tables = _load_tables(session)
    moves = tables["inventory_moves"]
    observations = tables["observations"]

    move_row = fetch_inventory_move_row(
        session,
        GetInventoryMoveRequest(move_id=request.move_id),
    )

    if move_row is None:
        return None, ()

    stmt = (
        select(
            observations.c.id.label("id"),
            observations.c.observed_at.label("observed_at"),
            observations.c.product_id.label("product_id"),
            observations.c.location_id.label("location_id"),
            observations.c.obs_type.label("obs_type"),
            observations.c.observed_qty.label("observed_qty"),
            observations.c.confidence.label("confidence"),
        )
        .select_from(observations)
        .where(observations.c.related_move_id == move_row["id"])
        .order_by(observations.c.observed_at.asc(), observations.c.id.asc())
    )

    observation_rows = session.execute(stmt).mappings().all()
    return move_row, observation_rows


def fetch_inventory_adjustments_summary(
    session: Session,
    request: GetInventoryAdjustmentsSummaryRequest,
) -> tuple[RowMapping, Sequence[RowMapping]]:
    tables = _load_tables(session)
    moves = tables["inventory_moves"]
    locations = tables["locations"]

    from_clause = moves.join(
        locations,
        or_(
            locations.c.id == moves.c.from_location_id,
            locations.c.id == moves.c.to_location_id,
        ),
    )

    conditions: list = [moves.c.move_type == "adjustment"]

    if request.warehouse_id:
        conditions.append(locations.c.warehouse_id == request.warehouse_id)
    if request.product_id:
        conditions.append(moves.c.product_id == request.product_id)
    if request.from_ts:
        conditions.append(moves.c.occurred_at >= request.from_ts)
    if request.to_ts:
        conditions.append(moves.c.occurred_at <= request.to_ts)

    base_stmt = select(
        moves.c.id,
        moves.c.qty,
        moves.c.reason_code,
    ).select_from(from_clause)

    if conditions:
        base_stmt = base_stmt.where(*conditions)

    base_subq = base_stmt.subquery("adjustments")

    summary_stmt = select(
        func.count(base_subq.c.id).label("count"),
        func.coalesce(func.sum(base_subq.c.qty), 0.0).label("total_qty"),
    )

    summary_row = session.execute(summary_stmt).mappings().one()

    breakdown_stmt = (
        select(
            base_subq.c.reason_code.label("reason_code"),
            func.count(base_subq.c.id).label("count"),
            func.coalesce(func.sum(base_subq.c.qty), 0.0).label("total_qty"),
        )
        .group_by(base_subq.c.reason_code)
        .order_by(base_subq.c.reason_code.asc())
    )

    breakdown_rows = session.execute(breakdown_stmt).mappings().all()
    return summary_row, breakdown_rows

