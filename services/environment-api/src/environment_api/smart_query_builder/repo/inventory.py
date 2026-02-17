from __future__ import annotations

from collections.abc import Sequence

from common.schemas.inventory import GetCurrentInventoryRequest
from database.inventory import InventoryBalance, Location, Product
from sqlalchemy import literal, select
from sqlalchemy.engine import RowMapping
from sqlalchemy.orm import Session
from sqlalchemy.sql.selectable import FromClause


def _load_tables(session: Session) -> dict[str, FromClause]:
    if session.get_bind() is None:
        raise RuntimeError("Database session is not bound.")

    return {
        "inventory_balances": InventoryBalance.__table__,
        "products": Product.__table__,
        "locations": Location.__table__,
    }


def fetch_current_inventory_rows(
    session: Session,
    request: GetCurrentInventoryRequest,
) -> Sequence[RowMapping]:
    tables = _load_tables(session)
    inventory_balances = tables["inventory_balances"]
    products = tables["products"]
    locations = tables["locations"]

    reserved_expr = inventory_balances.c.reserved if request.include_reserved else literal(0)
    available_expr = (inventory_balances.c.on_hand - reserved_expr).label("available")

    join_stmt = inventory_balances.join(
        products,
        inventory_balances.c.product_id == products.c.id,
    ).join(
        locations,
        inventory_balances.c.location_id == locations.c.id,
    )

    stmt = (
        select(
            locations.c.warehouse_id.label("warehouse_id"),
            locations.c.id.label("location_id"),
            locations.c.code.label("location_code"),
            products.c.id.label("product_id"),
            products.c.sku.label("sku"),
            inventory_balances.c.on_hand.label("on_hand"),
            reserved_expr.label("reserved"),
            available_expr,
            inventory_balances.c.quality_status.label("quality_status"),
            inventory_balances.c.last_count_at.label("last_count_at"),
        )
        .select_from(join_stmt)
        .order_by(available_expr.asc(), products.c.sku.asc())
        .limit(request.limit)
        .offset(request.offset)
    )

    if request.location_id:
        stmt = stmt.where(locations.c.id == request.location_id)
    elif request.warehouse_id:
        stmt = stmt.where(locations.c.warehouse_id == request.warehouse_id)

    if request.sku:
        stmt = stmt.where(products.c.sku == request.sku)
    if request.product_id:
        stmt = stmt.where(products.c.id == request.product_id)

    return session.execute(stmt).mappings().all()
