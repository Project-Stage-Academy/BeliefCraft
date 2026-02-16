from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from schemas.shipments import GetShipmentsDelaySummaryRequest
from sqlalchemy import MetaData, Table, and_, case, func, literal, or_, select
from sqlalchemy.engine import RowMapping
from sqlalchemy.orm import Session


def _load_shipments_table(session: Session) -> Table:
    bind = session.get_bind()
    if bind is None:
        raise RuntimeError("Database session is not bound.")

    metadata = MetaData()
    return Table("shipments", metadata, autoload_with=bind)


def fetch_shipments_delay_summary(
    session: Session,
    request: GetShipmentsDelaySummaryRequest,
) -> tuple[RowMapping, Sequence[RowMapping]]:
    shipments = _load_shipments_table(session)
    delayed_cutoff = datetime.now(UTC) - timedelta(hours=48)

    transit_hours_expr = case(
        (
            shipments.c.arrived_at.is_not(None),
            func.extract("epoch", shipments.c.arrived_at - shipments.c.shipped_at) / 3600.0,
        ),
        else_=None,
    )

    delayed_flag_expr = or_(
        and_(shipments.c.arrived_at.is_(None), shipments.c.shipped_at < delayed_cutoff),
        transit_hours_expr > 48,
    )

    delayed_reason_expr = case(
        (
            and_(shipments.c.arrived_at.is_(None), shipments.c.shipped_at < delayed_cutoff),
            literal("In transit over 48 hours"),
        ),
        (
            and_(shipments.c.arrived_at.is_not(None), transit_hours_expr > 48),
            literal("Transit exceeded 48 hours"),
        ),
        else_=literal("Not delayed"),
    )

    base_stmt = select(
        shipments.c.id.label("shipment_id"),
        shipments.c.status.label("status"),
        shipments.c.route_id.label("route_id"),
        shipments.c.origin_warehouse_id.label("origin_warehouse_id"),
        shipments.c.destination_warehouse_id.label("destination_warehouse_id"),
        shipments.c.shipped_at.label("shipped_at"),
        shipments.c.arrived_at.label("arrived_at"),
        transit_hours_expr.label("transit_hours"),
        delayed_flag_expr.label("is_delayed"),
        delayed_reason_expr.label("delayed_reason"),
    ).where(
        shipments.c.shipped_at.is_not(None),
        shipments.c.shipped_at >= request.date_from,
        shipments.c.shipped_at <= request.date_to,
    )

    if request.warehouse_id:
        base_stmt = base_stmt.where(
            or_(
                shipments.c.origin_warehouse_id == request.warehouse_id,
                shipments.c.destination_warehouse_id == request.warehouse_id,
            )
        )
    if request.route_id:
        base_stmt = base_stmt.where(shipments.c.route_id == request.route_id)
    if request.status:
        base_stmt = base_stmt.where(shipments.c.status == request.status)

    base = base_stmt.subquery("shipment_base")

    summary_stmt = select(
        func.count().label("total_shipments"),
        func.coalesce(func.sum(case((base.c.arrived_at.is_not(None), 1), else_=0)), 0).label(
            "delivered_count"
        ),
        func.coalesce(func.sum(case((base.c.arrived_at.is_(None), 1), else_=0)), 0).label(
            "in_transit_count"
        ),
        func.coalesce(func.sum(case((base.c.is_delayed.is_(True), 1), else_=0)), 0).label(
            "delayed_count"
        ),
        func.avg(case((base.c.arrived_at.is_not(None), base.c.transit_hours), else_=None)).label(
            "avg_transit_hours"
        ),
    )

    delayed_stmt = (
        select(
            base.c.shipment_id,
            base.c.status,
            base.c.route_id,
            base.c.origin_warehouse_id,
            base.c.destination_warehouse_id,
            base.c.shipped_at,
            base.c.arrived_at,
            base.c.transit_hours,
            base.c.delayed_reason,
        )
        .where(base.c.is_delayed.is_(True))
        .order_by(base.c.shipped_at.asc())
        .limit(20)
    )

    summary_row = session.execute(summary_stmt).mappings().one()
    delayed_rows = session.execute(delayed_stmt).mappings().all()
    return summary_row, delayed_rows
