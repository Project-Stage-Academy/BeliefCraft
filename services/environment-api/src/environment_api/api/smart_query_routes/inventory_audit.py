from __future__ import annotations

from datetime import datetime
from typing import Any

from environment_api.smart_query_builder.tools import (
    get_inventory_adjustments_summary,
    get_inventory_move,
    get_inventory_move_audit_trace,
    list_inventory_moves,
)
from fastapi import APIRouter, Query

from .common import execute_tool

router = APIRouter(prefix="/inventory", tags=["smart-query"])


@router.get("/moves")
def inventory_list_moves(
    warehouse_id: str | None = None,
    product_id: str | None = None,
    sku: str | None = None,
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
            sku=sku,
            move_type=move_type,
            from_ts=from_ts,
            to_ts=to_ts,
            limit=limit,
            offset=offset,
        )
    )


@router.get("/moves/{move_id}")
def inventory_get_move(move_id: str) -> dict[str, Any]:
    return execute_tool(lambda: get_inventory_move(move_id=move_id))


@router.get("/moves/{move_id}/audit-trace")
def inventory_get_move_audit_trace(move_id: str) -> dict[str, Any]:
    return execute_tool(lambda: get_inventory_move_audit_trace(move_id=move_id))


@router.get("/adjustments-summary")
def inventory_adjustments_summary(
    warehouse_id: str | None = None,
    product_id: str | None = None,
    sku: str | None = None,
    from_ts: datetime | None = None,
    to_ts: datetime | None = None,
) -> dict[str, Any]:
    return execute_tool(
        lambda: get_inventory_adjustments_summary(
            warehouse_id=warehouse_id,
            product_id=product_id,
            sku=sku,
            from_ts=from_ts,
            to_ts=to_ts,
        )
    )
