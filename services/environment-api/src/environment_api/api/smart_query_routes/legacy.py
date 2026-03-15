from __future__ import annotations

import importlib
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Query

from .common import execute_tool

router = APIRouter(tags=["smart-query"])


@router.get("/inventory/current", deprecated=True)
def current_inventory_legacy(
    warehouse_id: str | None = None,
    location_id: str | None = None,
    sku: str | None = None,
    product_id: str | None = None,
    include_reserved: bool = True,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    smart_query = importlib.import_module("environment_api.api.smart_query")
    get_current_inventory = smart_query.get_current_inventory

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


@router.get("/shipments/delay-summary", deprecated=True)
def shipments_delay_summary_legacy(
    date_from: datetime,
    date_to: datetime,
    warehouse_id: str | None = None,
    route_id: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
) -> dict[str, Any]:
    smart_query = importlib.import_module("environment_api.api.smart_query")
    get_shipments_delay_summary = smart_query.get_shipments_delay_summary

    return execute_tool(
        lambda: get_shipments_delay_summary(
            date_from=date_from,
            date_to=date_to,
            warehouse_id=warehouse_id,
            route_id=route_id,
            status=status_filter,
        )
    )


@router.get("/observations/compare-balances", deprecated=True)
def observations_compare_balances_legacy(
    observed_from: datetime,
    observed_to: datetime,
    warehouse_id: str | None = None,
    location_id: str | None = None,
    sku: str | None = None,
    product_id: str | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    smart_query = importlib.import_module("environment_api.api.smart_query")
    compare_observations_to_balances = smart_query.compare_observations_to_balances

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


@router.get("/orders/at-risk", deprecated=True)
def at_risk_orders_legacy(
    horizon_hours: int = Query(default=48, ge=1, le=720),
    min_sla_priority: float = Query(default=0.7, ge=0.0, le=1.0),
    status_filter: str | None = Query(default=None, alias="status"),
    top_missing_skus_limit: int = Query(default=5, ge=1, le=50),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    smart_query = importlib.import_module("environment_api.api.smart_query")
    get_at_risk_orders = smart_query.get_at_risk_orders

    return execute_tool(
        lambda: get_at_risk_orders(
            horizon_hours=horizon_hours,
            min_sla_priority=min_sla_priority,
            status=status_filter,
            top_missing_skus_limit=top_missing_skus_limit,
            limit=limit,
            offset=offset,
        )
    )
