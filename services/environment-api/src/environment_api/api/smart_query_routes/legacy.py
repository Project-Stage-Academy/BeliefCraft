from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status

router = APIRouter(tags=["smart-query"])

_LEGACY_DETAIL = (
    "This endpoint is deprecated and temporarily kept for compatibility while clients migrate."
)


def _deprecated_response() -> dict[str, Any]:
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail=_LEGACY_DETAIL,
    )


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
    return _deprecated_response()


@router.get("/shipments/delay-summary", deprecated=True)
def shipments_delay_summary_legacy(
    date_from: datetime,
    date_to: datetime,
    warehouse_id: str | None = None,
    route_id: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
) -> dict[str, Any]:
    return _deprecated_response()


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
    return _deprecated_response()


@router.get("/orders/at-risk", deprecated=True)
def at_risk_orders_legacy(
    horizon_hours: int = Query(default=48, ge=1, le=720),
    min_sla_priority: float = Query(default=0.7, ge=0.0, le=1.0),
    status_filter: str | None = Query(default=None, alias="status"),
    top_missing_skus_limit: int = Query(default=5, ge=1, le=50),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    return _deprecated_response()
