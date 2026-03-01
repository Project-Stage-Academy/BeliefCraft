from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from common.schemas.topology import TopologyLocationType
from environment_api.smart_query_builder.tools import (
    get_capacity_utilization_snapshot,
    get_location,
    get_locations_tree,
    get_warehouse,
    list_locations,
    list_warehouses,
)
from fastapi import APIRouter, Query

from .common import enum_value_or_raw, execute_tool

router = APIRouter(prefix="/topology", tags=["smart-query"])


@router.get("/warehouses")
def topology_list_warehouses(
    region: str | None = None,
    name_like: str | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    return execute_tool(
        lambda: list_warehouses(
            region=region,
            name_like=name_like,
            limit=limit,
            offset=offset,
        )
    )


@router.get("/warehouses/{warehouse_id}")
def topology_get_warehouse(warehouse_id: str) -> dict[str, Any]:
    return execute_tool(lambda: get_warehouse(warehouse_id=warehouse_id))


@router.get("/locations")
def topology_list_locations(
    warehouse_id: str | None = None,
    location_type: Annotated[TopologyLocationType | None, Query(alias="type")] = None,
    parent_location_id: str | None = None,
    code_like: str | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    return execute_tool(
        lambda: list_locations(
            warehouse_id=warehouse_id,
            type=enum_value_or_raw(location_type),
            parent_location_id=parent_location_id,
            code_like=code_like,
            limit=limit,
            offset=offset,
        )
    )


@router.get("/locations/{location_id}")
def topology_get_location(location_id: str) -> dict[str, Any]:
    return execute_tool(lambda: get_location(location_id=location_id))


@router.get("/warehouses/{warehouse_id}/locations-tree")
def topology_get_locations_tree(warehouse_id: str) -> dict[str, Any]:
    return execute_tool(lambda: get_locations_tree(warehouse_id=warehouse_id))


@router.get("/warehouses/{warehouse_id}/capacity-utilization")
def topology_capacity_utilization(
    warehouse_id: str,
    snapshot_at: datetime | None = None,
    observed_from: datetime | None = None,
    observed_to: datetime | None = None,
    lookback_hours: int = Query(default=24, ge=1, le=24 * 30),
    location_type: Annotated[TopologyLocationType | None, Query(alias="type")] = None,
) -> dict[str, Any]:
    return execute_tool(
        lambda: get_capacity_utilization_snapshot(
            warehouse_id=warehouse_id,
            snapshot_at=snapshot_at,
            observed_from=observed_from,
            observed_to=observed_to,
            lookback_hours=lookback_hours,
            type=enum_value_or_raw(location_type),
        )
    )
