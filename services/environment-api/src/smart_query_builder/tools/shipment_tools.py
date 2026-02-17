from __future__ import annotations

from datetime import datetime
from typing import Any

from schemas.common import ToolResult
from schemas.shipments import (
    DelayedShipmentRow,
    GetShipmentsDelaySummaryRequest,
    ShipmentsDelaySummary,
)

from ..db.session import get_session
from ..repo.shipments import fetch_shipments_delay_summary


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _to_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def get_shipments_delay_summary(
    date_from: datetime,
    date_to: datetime,
    warehouse_id: str | None = None,
    route_id: str | None = None,
    status: str | None = None,
) -> ToolResult[ShipmentsDelaySummary]:
    """
    USE THIS TOOL whenever you need shipment delay analytics in a time range,
    including both KPI summary and a top delayed shipments list.

    This tool is useful for operations reviews, exception tracking, and route-level diagnostics.
    """
    try:
        request = GetShipmentsDelaySummaryRequest(
            date_from=date_from,
            date_to=date_to,
            warehouse_id=warehouse_id,
            route_id=route_id,
            status=status,
        )

        with get_session() as session:
            summary_row, delayed_rows = fetch_shipments_delay_summary(session, request)

        delayed_shipments = [
            DelayedShipmentRow(
                shipment_id=str(row["shipment_id"]),
                status=_to_str(row["status"]),
                route_id=_to_str(row["route_id"]),
                origin_warehouse_id=_to_str(row["origin_warehouse_id"]),
                destination_warehouse_id=_to_str(row["destination_warehouse_id"]),
                shipped_at=row["shipped_at"],
                arrived_at=row["arrived_at"],
                transit_hours=_to_float(row["transit_hours"]),
                delayed_reason=str(row["delayed_reason"]),
            )
            for row in delayed_rows
        ]

        summary = ShipmentsDelaySummary(
            total_shipments=int(summary_row["total_shipments"] or 0),
            delivered_count=int(summary_row["delivered_count"] or 0),
            in_transit_count=int(summary_row["in_transit_count"] or 0),
            delayed_count=int(summary_row["delayed_count"] or 0),
            avg_transit_hours=_to_float(summary_row["avg_transit_hours"]),
            delayed_shipments=delayed_shipments,
        )

        message = (
            "No results for shipment delay summary."
            if summary.total_shipments == 0
            else f"Analyzed {summary.total_shipments} shipments."
        )

        return ToolResult(
            data=summary,
            message=message,
            meta={
                "filters": {
                    "date_from": request.date_from.isoformat(),
                    "date_to": request.date_to.isoformat(),
                    "warehouse_id": warehouse_id,
                    "route_id": route_id,
                    "status": status,
                },
                "delayed_list_count": len(delayed_shipments),
            },
        )
    except Exception as exc:
        raise RuntimeError("Unable to fetch shipment delay summary.") from exc
