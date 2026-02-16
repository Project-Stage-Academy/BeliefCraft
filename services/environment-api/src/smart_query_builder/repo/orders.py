from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from schemas.orders import GetAtRiskOrdersRequest
from sqlalchemy import MetaData, Table, and_, case, func, or_, select
from sqlalchemy.dialects.postgresql import aggregate_order_by
from sqlalchemy.engine import RowMapping
from sqlalchemy.orm import Session


def _load_tables(session: Session) -> dict[str, Table]:
    bind = session.get_bind()
    if bind is None:
        raise RuntimeError("Database session is not bound.")

    metadata = MetaData()
    return {
        "orders": Table("orders", metadata, autoload_with=bind),
        "order_lines": Table("order_lines", metadata, autoload_with=bind),
        "products": Table("products", metadata, autoload_with=bind),
    }


def fetch_at_risk_order_rows(
    session: Session,
    request: GetAtRiskOrdersRequest,
) -> Sequence[RowMapping]:
    tables = _load_tables(session)
    orders = tables["orders"]
    order_lines = tables["order_lines"]
    products = tables["products"]

    now_utc = datetime.now(UTC)
    horizon_cutoff = now_utc + timedelta(hours=request.horizon_hours)
    urgent_cutoff = now_utc + timedelta(hours=24)

    open_qty_expr = func.greatest(order_lines.c.qty_ordered - order_lines.c.qty_allocated, 0)
    risk_line_expr = or_(
        open_qty_expr > 0,
        and_(
            order_lines.c.qty_shipped < order_lines.c.qty_ordered,
            orders.c.promised_at <= urgent_cutoff,
        ),
    )

    base_filters = [
        orders.c.promised_at.is_not(None),
        orders.c.promised_at <= horizon_cutoff,
        orders.c.sla_priority >= request.min_sla_priority,
    ]
    if request.status:
        base_filters.append(orders.c.status == request.status)

    joined = orders.join(order_lines, order_lines.c.order_id == orders.c.id).join(
        products, products.c.id == order_lines.c.product_id
    )

    risk_line_count_expr = func.sum(case((risk_line_expr, 1), else_=0))

    aggregates = (
        select(
            orders.c.id.label("order_id"),
            orders.c.status.label("status"),
            orders.c.promised_at.label("promised_at"),
            orders.c.sla_priority.label("sla_priority"),
            func.count(order_lines.c.id).label("total_lines"),
            func.coalesce(
                func.sum(case((open_qty_expr > 0, open_qty_expr), else_=0)),
                0,
            ).label("total_open_qty"),
            func.coalesce(
                func.sum(
                    case(
                        (open_qty_expr > 0, order_lines.c.service_level_penalty * open_qty_expr),
                        else_=0.0,
                    )
                ),
                0.0,
            ).label("total_penalty_exposure"),
            risk_line_count_expr.label("risk_line_count"),
        )
        .select_from(joined)
        .where(*base_filters)
        .group_by(
            orders.c.id,
            orders.c.status,
            orders.c.promised_at,
            orders.c.sla_priority,
        )
        .having(risk_line_count_expr > 0)
        .subquery("aggregates")
    )

    ranked_missing = (
        select(
            orders.c.id.label("order_id"),
            products.c.sku.label("sku"),
            open_qty_expr.label("open_qty"),
            func.row_number()
            .over(
                partition_by=orders.c.id,
                order_by=(open_qty_expr.desc(), products.c.sku.asc()),
            )
            .label("rn"),
        )
        .select_from(joined)
        .where(*base_filters, open_qty_expr > 0)
        .subquery("ranked_missing")
    )

    top_missing = (
        select(
            ranked_missing.c.order_id,
            func.array_agg(
                aggregate_order_by(ranked_missing.c.sku, ranked_missing.c.rn.asc())
            ).label("top_missing_skus"),
        )
        .where(ranked_missing.c.rn <= 5)
        .group_by(ranked_missing.c.order_id)
        .subquery("top_missing")
    )

    stmt = (
        select(
            aggregates.c.order_id,
            aggregates.c.status,
            aggregates.c.promised_at,
            aggregates.c.sla_priority,
            aggregates.c.total_lines,
            aggregates.c.total_open_qty,
            aggregates.c.total_penalty_exposure,
            top_missing.c.top_missing_skus,
        )
        .select_from(
            aggregates.outerjoin(top_missing, top_missing.c.order_id == aggregates.c.order_id)
        )
        .order_by(aggregates.c.total_penalty_exposure.desc(), aggregates.c.promised_at.asc())
        .limit(request.limit)
        .offset(request.offset)
    )

    return session.execute(stmt).mappings().all()
