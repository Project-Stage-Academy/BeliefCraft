from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Query
from src.smart_query_builder.tools import (
    compare_observations_to_balances,
    get_at_risk_orders,
    get_current_inventory,
    get_shipments_delay_summary,
)

router = APIRouter(prefix="/smart-query", tags=["smart-query"])


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
    result = get_current_inventory(
        warehouse_id=warehouse_id,
        location_id=location_id,
        sku=sku,
        product_id=product_id,
        include_reserved=include_reserved,
        limit=limit,
        offset=offset,
    )
    return result.model_dump(mode="json")


@router.get("/shipments/delay-summary")
def shipments_delay_summary(
    date_from: datetime,
    date_to: datetime,
    warehouse_id: str | None = None,
    route_id: str | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    result = get_shipments_delay_summary(
        date_from=date_from,
        date_to=date_to,
        warehouse_id=warehouse_id,
        route_id=route_id,
        status=status,
    )
    return result.model_dump(mode="json")


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
    result = compare_observations_to_balances(
        observed_from=observed_from,
        observed_to=observed_to,
        warehouse_id=warehouse_id,
        location_id=location_id,
        sku=sku,
        product_id=product_id,
        limit=limit,
        offset=offset,
    )
    return result.model_dump(mode="json")


@router.get("/orders/at-risk")
def at_risk_orders(
    horizon_hours: int = Query(default=48, ge=1, le=24 * 30),
    min_sla_priority: float = Query(default=0.7, ge=0.0, le=1.0),
    status: str | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    result = get_at_risk_orders(
        horizon_hours=horizon_hours,
        min_sla_priority=min_sla_priority,
        status=status,
        limit=limit,
        offset=offset,
    )
    return result.model_dump(mode="json")
