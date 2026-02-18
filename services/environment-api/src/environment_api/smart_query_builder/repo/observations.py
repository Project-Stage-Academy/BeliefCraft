from __future__ import annotations

from collections.abc import Sequence

from common.schemas.observations import CompareObservationsToBalancesRequest
from sqlalchemy import MetaData, Table, func, select
from sqlalchemy.engine import RowMapping
from sqlalchemy.orm import Session


def _load_tables(session: Session) -> dict[str, Table]:
    bind = session.get_bind()
    if bind is None:
        raise RuntimeError("Database session is not bound.")

    metadata = MetaData()
    return {
        "observations": Table("observations", metadata, autoload_with=bind),
        "products": Table("products", metadata, autoload_with=bind),
        "locations": Table("locations", metadata, autoload_with=bind),
        "warehouses": Table("warehouses", metadata, autoload_with=bind),
        "inventory_balances": Table("inventory_balances", metadata, autoload_with=bind),
    }


def fetch_observation_vs_balance_rows(
    session: Session,
    request: CompareObservationsToBalancesRequest,
) -> Sequence[RowMapping]:
    tables = _load_tables(session)
    observations = tables["observations"]
    products = tables["products"]
    locations = tables["locations"]
    warehouses = tables["warehouses"]
    inventory_balances = tables["inventory_balances"]

    confidence_weight = func.coalesce(observations.c.confidence, 0.0)
    observed_estimate_expr = (
        func.sum(observations.c.observed_qty * confidence_weight)
        / func.nullif(func.sum(confidence_weight), 0)
    ).label("observed_estimate")

    aggregated_stmt = (
        select(
            warehouses.c.id.label("warehouse_id"),
            locations.c.id.label("location_id"),
            products.c.sku.label("sku"),
            products.c.id.label("product_id"),
            observed_estimate_expr,
            inventory_balances.c.on_hand.label("on_hand"),
            inventory_balances.c.reserved.label("reserved"),
            (inventory_balances.c.on_hand - inventory_balances.c.reserved).label("available"),
            func.count(observations.c.id).label("obs_count"),
            func.avg(observations.c.confidence).label("avg_confidence"),
        )
        .select_from(
            observations.join(products, observations.c.product_id == products.c.id)
            .join(locations, observations.c.location_id == locations.c.id)
            .join(warehouses, locations.c.warehouse_id == warehouses.c.id)
            .join(
                inventory_balances,
                (inventory_balances.c.product_id == observations.c.product_id)
                & (inventory_balances.c.location_id == observations.c.location_id),
            )
        )
        .where(
            observations.c.observed_at >= request.observed_from,
            observations.c.observed_at <= request.observed_to,
            observations.c.is_missing.is_(False),
            observations.c.observed_qty.is_not(None),
        )
        .group_by(
            warehouses.c.id,
            locations.c.id,
            products.c.sku,
            products.c.id,
            inventory_balances.c.on_hand,
            inventory_balances.c.reserved,
        )
    )

    if request.warehouse_id:
        aggregated_stmt = aggregated_stmt.where(warehouses.c.id == request.warehouse_id)
    if request.location_id:
        aggregated_stmt = aggregated_stmt.where(locations.c.id == request.location_id)
    if request.sku:
        aggregated_stmt = aggregated_stmt.where(products.c.sku == request.sku)
    if request.product_id:
        aggregated_stmt = aggregated_stmt.where(products.c.id == request.product_id)

    summary = aggregated_stmt.subquery("observation_summary")
    discrepancy_expr = (summary.c.observed_estimate - summary.c.on_hand).label("discrepancy")

    stmt = (
        select(
            summary.c.warehouse_id,
            summary.c.location_id,
            summary.c.sku,
            summary.c.product_id,
            summary.c.observed_estimate,
            summary.c.on_hand,
            summary.c.reserved,
            summary.c.available,
            discrepancy_expr,
            summary.c.obs_count,
            summary.c.avg_confidence,
        )
        .order_by(func.abs(discrepancy_expr).desc(), summary.c.sku.asc())
        .limit(request.limit)
        .offset(request.offset)
    )

    return session.execute(stmt).mappings().all()
