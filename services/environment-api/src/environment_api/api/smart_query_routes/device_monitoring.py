from __future__ import annotations

from datetime import datetime
from typing import Any

from environment_api.smart_query_builder.tools import (
    get_device_anomalies,
    get_device_health_summary,
    get_sensor_device,
    list_sensor_devices,
)
from fastapi import APIRouter, Query

from .common import execute_tool

router = APIRouter(prefix="/devices", tags=["smart-query"])


@router.get("")
def devices_list(
    warehouse_id: str | None = None,
    device_type: str | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    return execute_tool(
        lambda: list_sensor_devices(
            warehouse_id=warehouse_id,
            device_type=device_type,
            status=status,
        )
    )


@router.get("/health-summary")
def devices_health_summary(
    warehouse_id: str | None = None,
    since_ts: datetime | None = None,
    as_of: datetime | None = None,
) -> dict[str, Any]:
    return execute_tool(
        lambda: get_device_health_summary(
            warehouse_id=warehouse_id,
            since_ts=since_ts,
            as_of=as_of,
        )
    )


@router.get("/anomalies")
def devices_anomalies(
    warehouse_id: str | None = None,
    window: int = Query(default=24, ge=1, le=24 * 30),
) -> dict[str, Any]:
    return execute_tool(
        lambda: get_device_anomalies(
            warehouse_id=warehouse_id,
            window=window,
        )
    )


@router.get("/{device_id}")
def devices_get(device_id: str) -> dict[str, Any]:
    return execute_tool(lambda: get_sensor_device(device_id=device_id))
