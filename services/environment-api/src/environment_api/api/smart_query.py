from __future__ import annotations

from datetime import datetime
from typing import Any

from environment_api.api.smart_query_routes import procurement_router
from environment_api.api.smart_query_routes.common import execute_tool
from environment_api.smart_query_builder.tools import (
    compare_observations_to_balances,
    get_at_risk_orders,
    get_current_inventory,
    get_inventory_adjustments_summary,
    get_inventory_move,
    get_inventory_move_audit_trace,
    get_shipments_delay_summary,
    list_inventory_moves,
)
from fastapi import APIRouter, Query

router = APIRouter(prefix="/smart-query", tags=["smart-query"])
router.include_router(procurement_router)


@router.get("/inventory/current")
def current_inventory(
    warehouse_id: str | None = None,
    location_id: str | None = None,
    sku: str | None = None,
    product_id: str | None = None,
    include_reserved: bool = True,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    return execute_tool(
        lambda: get_current_inventory(
            warehouse_id=warehouse_id,
            location_id=location_id,
            sku=sku,
            product_id=product_id,
            include_reserved=include_reserved,
            limit=limit,
            offset=offset,
        )
    )


@router.get("/inventory/moves")
def inventory_list_moves(
    warehouse_id: str | None = None,
    product_id: str | None = None,
    move_type: str | None = None,
    from_ts: datetime | None = None,
    to_ts: datetime | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    return execute_tool(
        lambda: list_inventory_moves(
            warehouse_id=warehouse_id,
            product_id=product_id,
            move_type=move_type,
            from_ts=from_ts,
            to_ts=to_ts,
            limit=limit,
            offset=offset,
        )
    )


@router.get("/inventory/moves/{move_id}")
def inventory_get_move(
    move_id: str,
) -> dict[str, Any]:
    return execute_tool(lambda: get_inventory_move(move_id=move_id))


@router.get("/inventory/moves/{move_id}/audit-trace")
def inventory_get_move_audit_trace(
    move_id: str,
) -> dict[str, Any]:
    return execute_tool(lambda: get_inventory_move_audit_trace(move_id=move_id))


@router.get("/inventory/adjustments-summary")
def inventory_adjustments_summary(
    warehouse_id: str | None = None,
    product_id: str | None = None,
    from_ts: datetime | None = None,
    to_ts: datetime | None = None,
) -> dict[str, Any]:
    return execute_tool(
        lambda: get_inventory_adjustments_summary(
            warehouse_id=warehouse_id,
            product_id=product_id,
            from_ts=from_ts,
            to_ts=to_ts,
        )
    )


@router.get("/shipments/delay-summary")
def shipments_delay_summary(
    date_from: datetime,
    date_to: datetime,
    warehouse_id: str | None = None,
    route_id: str | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    return execute_tool(
        lambda: get_shipments_delay_summary(
            date_from=date_from,
            date_to=date_to,
            warehouse_id=warehouse_id,
            route_id=route_id,
            status=status,
        )
    )


@router.get("/observations/compare-balances")
def observations_compare_balances(
    observed_from: datetime,
    observed_to: datetime,
    warehouse_id: str | None = None,
    location_id: str | None = None,
    sku: str | None = None,
    product_id: str | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    return execute_tool(
        lambda: compare_observations_to_balances(
            observed_from=observed_from,
            observed_to=observed_to,
            warehouse_id=warehouse_id,
            location_id=location_id,
            sku=sku,
            product_id=product_id,
            limit=limit,
            offset=offset,
        )
    )


@router.get("/orders/at-risk")
def at_risk_orders(
    horizon_hours: int = Query(default=48, ge=1, le=24 * 30),
    min_sla_priority: float = Query(default=0.7, ge=0.0, le=1.0),
    status: str | None = None,
    top_missing_skus_limit: int = Query(default=5, ge=1, le=50),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    return execute_tool(
        lambda: get_at_risk_orders(
            horizon_hours=horizon_hours,
            min_sla_priority=min_sla_priority,
            status=status,
            top_missing_skus_limit=top_missing_skus_limit,
            limit=limit,
            offset=offset,
        )
    )
