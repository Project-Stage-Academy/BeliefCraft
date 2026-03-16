from __future__ import annotations

from typing import Any

from environment_api.smart_query_builder.tools import get_observed_inventory_snapshot
from fastapi import APIRouter

from .common import execute_tool

router = APIRouter(prefix="/inventory", tags=["smart-query"])


def _split_csv_or_none(raw: str | None) -> list[str] | None:
    if raw is None:
        return None

    values = [part.strip() for part in raw.split(",") if part.strip()]
    return values or None


@router.get("/observed-snapshot")
def observed_inventory_snapshot(
    quality_status_in: str | None = None,
    dev_mode: bool = False,
) -> dict[str, Any]:
    return execute_tool(
        lambda: get_observed_inventory_snapshot(
            quality_status_in=_split_csv_or_none(quality_status_in),
            dev_mode=dev_mode,
        )
    )
