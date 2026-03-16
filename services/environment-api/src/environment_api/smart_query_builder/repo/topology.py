from __future__ import annotations

from collections.abc import Sequence
from datetime import timedelta
from typing import Any

from common.schemas.topology import (
    GetLocationRequest,
    GetWarehouseCapacityUtilizationRequest,
    GetWarehouseLocationsTreeRequest,
    GetWarehouseRequest,
    ListLocationsRequest,
    ListWarehousesRequest,
)
from database.inventory import Location
from database.logistics import Warehouse
from database.observations import Observation
from sqlalchemy import case, func, select
from sqlalchemy.engine import RowMapping
from sqlalchemy.orm import Session
from sqlalchemy.sql.selectable import FromClause

from ._table_utils import load_tables

_TOPOLOGY_TABLES: dict[str, FromClause] = {
    "warehouses": Warehouse.__table__,
    "locations": Location.__table__,
    "observations": Observation.__table__,
}


def _enum_storage_value(value: object) -> str:
    if hasattr(value, "name"):
        return str(value.name)

    enum_value = value.value if hasattr(value, "value") else value
    return str(enum_value).upper()


def fetch_warehouse_rows(
    session: Session,
    request: ListWarehousesRequest,
) -> Sequence[RowMapping]:
    tables = load_tables(session, _TOPOLOGY_TABLES)
    warehouses = tables["warehouses"]

    stmt = (
        select(
            warehouses.c.id.label("id"),
            warehouses.c.name.label("name"),
            warehouses.c.region.label("region"),
            warehouses.c.tz.label("tz"),
        )
        .select_from(warehouses)
        .order_by(warehouses.c.name.asc(), warehouses.c.id.asc())
        .limit(request.limit)
        .offset(request.offset)
    )

    if request.region:
        stmt = stmt.where(warehouses.c.region == request.region)
    if request.name_like:
        stmt = stmt.where(warehouses.c.name.ilike(f"%{request.name_like}%"))

    return session.execute(stmt).mappings().all()


def fetch_warehouse_row(
    session: Session,
    request: GetWarehouseRequest,
) -> RowMapping | None:
    tables = load_tables(session, _TOPOLOGY_TABLES)
    warehouses = tables["warehouses"]

    stmt = (
        select(
            warehouses.c.id.label("id"),
            warehouses.c.name.label("name"),
            warehouses.c.region.label("region"),
            warehouses.c.tz.label("tz"),
        )
        .select_from(warehouses)
        .where(warehouses.c.id == request.warehouse_id)
        .limit(1)
    )

    return session.execute(stmt).mappings().one_or_none()


def fetch_location_rows(
    session: Session,
    request: ListLocationsRequest,
) -> Sequence[RowMapping]:
    tables = load_tables(session, _TOPOLOGY_TABLES)
    locations = tables["locations"]

    stmt = (
        select(
            locations.c.id.label("id"),
            locations.c.warehouse_id.label("warehouse_id"),
            locations.c.parent_location_id.label("parent_location_id"),
            locations.c.code.label("code"),
            locations.c.type.label("type"),
            locations.c.capacity_units.label("capacity_units"),
        )
        .select_from(locations)
        .order_by(locations.c.code.asc(), locations.c.id.asc())
        .limit(request.limit)
        .offset(request.offset)
    )

    if request.warehouse_id:
        stmt = stmt.where(locations.c.warehouse_id == request.warehouse_id)
    if request.parent_location_id:
        stmt = stmt.where(locations.c.parent_location_id == request.parent_location_id)
    if request.type:
        stmt = stmt.where(locations.c.type == _enum_storage_value(request.type))
    if request.code_like:
        stmt = stmt.where(locations.c.code.ilike(f"%{request.code_like}%"))

    return session.execute(stmt).mappings().all()


def fetch_location_row(
    session: Session,
    request: GetLocationRequest,
) -> RowMapping | None:
    tables = load_tables(session, _TOPOLOGY_TABLES)
    locations = tables["locations"]

    stmt = (
        select(
            locations.c.id.label("id"),
            locations.c.warehouse_id.label("warehouse_id"),
            locations.c.parent_location_id.label("parent_location_id"),
            locations.c.code.label("code"),
            locations.c.type.label("type"),
            locations.c.capacity_units.label("capacity_units"),
        )
        .select_from(locations)
        .where(locations.c.id == request.location_id)
        .limit(1)
    )

    return session.execute(stmt).mappings().one_or_none()


def fetch_warehouse_location_rows(
    session: Session,
    request: GetWarehouseLocationsTreeRequest,
) -> Sequence[RowMapping]:
    tables = load_tables(session, _TOPOLOGY_TABLES)
    locations = tables["locations"]

    stmt = (
        select(
            locations.c.id.label("id"),
            locations.c.warehouse_id.label("warehouse_id"),
            locations.c.parent_location_id.label("parent_location_id"),
            locations.c.code.label("code"),
            locations.c.type.label("type"),
            locations.c.capacity_units.label("capacity_units"),
        )
        .select_from(locations)
        .where(locations.c.warehouse_id == request.warehouse_id)
        .order_by(locations.c.code.asc(), locations.c.id.asc())
    )

    return session.execute(stmt).mappings().all()


def _resolve_observation_window(
    request: GetWarehouseCapacityUtilizationRequest,
) -> tuple[Any, Any]:
    if request.snapshot_at is not None:
        observed_to = request.snapshot_at
        observed_from = request.snapshot_at - timedelta(hours=request.lookback_hours)
        return observed_from, observed_to

    if request.observed_from is None or request.observed_to is None:
        raise RuntimeError("Expected observed_from and observed_to for range mode.")

    return request.observed_from, request.observed_to


def _build_filtered_observations_subquery(
    locations: Any,
    observations: Any,
    request: GetWarehouseCapacityUtilizationRequest,
    observed_from: Any,
    observed_to: Any,
) -> Any:
    filtered_obs_stmt = (
        select(
            observations.c.id.label("observation_id"),
            observations.c.location_id.label("location_id"),
            observations.c.product_id.label("product_id"),
            observations.c.observed_qty.label("observed_qty"),
            observations.c.confidence.label("confidence"),
        )
        .select_from(observations.join(locations, observations.c.location_id == locations.c.id))
        .where(
            locations.c.warehouse_id == request.warehouse_id,
            observations.c.observed_at >= observed_from,
            observations.c.observed_at <= observed_to,
            observations.c.is_missing.is_(False),
            observations.c.observed_qty.is_not(None),
            observations.c.confidence.is_not(None),
        )
    )

    if request.type:
        filtered_obs_stmt = filtered_obs_stmt.where(
            locations.c.type == _enum_storage_value(request.type)
        )

    return filtered_obs_stmt.subquery("filtered_observations")


def _build_pair_estimates_subquery(filtered_obs: Any) -> Any:
    return (
        select(
            filtered_obs.c.location_id,
            filtered_obs.c.product_id,
            (
                func.sum(filtered_obs.c.observed_qty * filtered_obs.c.confidence)
                / func.nullif(func.sum(filtered_obs.c.confidence), 0)
            ).label("qty_hat"),
            func.avg(filtered_obs.c.confidence).label("conf_hat"),
            func.count(filtered_obs.c.observation_id).label("obs_count"),
        )
        .group_by(filtered_obs.c.location_id, filtered_obs.c.product_id)
        .subquery("pair_estimates")
    )


def _build_location_estimates_subquery(pair_estimates: Any) -> Any:
    return (
        select(
            pair_estimates.c.location_id,
            func.sum(pair_estimates.c.qty_hat).label("observed_qty_sum"),
            func.avg(pair_estimates.c.conf_hat).label("confidence_avg"),
            func.sum(pair_estimates.c.obs_count).label("obs_count"),
        )
        .group_by(pair_estimates.c.location_id)
        .subquery("location_estimates")
    )


def _build_capacity_utilization_stmt(
    locations: Any,
    location_estimates: Any,
    request: GetWarehouseCapacityUtilizationRequest,
) -> Any:
    utilization_expr = case(
        (
            (locations.c.capacity_units > 0) & location_estimates.c.observed_qty_sum.is_not(None),
            location_estimates.c.observed_qty_sum / locations.c.capacity_units,
        ),
        else_=None,
    ).label("utilization_estimate")

    stmt = (
        select(
            locations.c.id.label("location_id"),
            locations.c.capacity_units.label("capacity_units"),
            location_estimates.c.observed_qty_sum.label("observed_qty_sum"),
            utilization_expr,
            location_estimates.c.confidence_avg.label("confidence_avg"),
            func.coalesce(location_estimates.c.obs_count, 0).label("obs_count"),
        )
        .select_from(
            locations.outerjoin(
                location_estimates,
                location_estimates.c.location_id == locations.c.id,
            )
        )
        .where(locations.c.warehouse_id == request.warehouse_id)
        .order_by(
            utilization_expr.desc().nulls_last(),
            locations.c.code.asc(),
            locations.c.id.asc(),
        )
    )

    if request.type:
        stmt = stmt.where(locations.c.type == _enum_storage_value(request.type))

    return stmt


def fetch_capacity_utilization_rows(
    session: Session,
    request: GetWarehouseCapacityUtilizationRequest,
) -> Sequence[RowMapping]:
    tables = load_tables(session, _TOPOLOGY_TABLES)
    locations = tables["locations"]
    observations = tables["observations"]

    observed_from, observed_to = _resolve_observation_window(request)

    filtered_obs = _build_filtered_observations_subquery(
        locations=locations,
        observations=observations,
        request=request,
        observed_from=observed_from,
        observed_to=observed_to,
    )
    pair_estimates = _build_pair_estimates_subquery(filtered_obs)
    location_estimates = _build_location_estimates_subquery(pair_estimates)
    stmt = _build_capacity_utilization_stmt(locations, location_estimates, request)

    return session.execute(stmt).mappings().all()
