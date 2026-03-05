from __future__ import annotations

from datetime import datetime
from typing import Any

from common.schemas.common import ToolResult
from common.schemas.inventory import (
    GetInventoryAdjustmentsSummaryRequest,
    GetInventoryAdjustmentsSummaryResponse,
    GetInventoryMoveAuditTraceRequest,
    GetInventoryMoveAuditTraceResponse,
    GetInventoryMoveRequest,
    GetInventoryMoveResponse,
    InventoryAdjustmentByReason,
    InventoryMoveRow,
    ListInventoryMovesRequest,
    ListInventoryMovesResponse,
    ObservationForMove,
)

from ..db.session import get_session
from ..repo.inventory_moves import (
    fetch_inventory_adjustments_summary,
    fetch_inventory_move_audit_trace_rows,
    fetch_inventory_move_row,
    fetch_inventory_move_rows,
)


def _to_float(value: Any, field_name: str) -> float:
    if value is None:
        raise ValueError(f"Unexpected null value for {field_name}.")
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid numeric value for {field_name}: {value!r}") from exc


def _to_int(value: Any, field_name: str) -> int:
    if value is None:
        raise ValueError(f"Unexpected null value for {field_name}.")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid integer value for {field_name}: {value!r}") from exc


def _to_str(value: Any) -> str:
    return "" if value is None else str(value)


def _to_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _inventory_move_from_row(row: Any) -> InventoryMoveRow:
    return InventoryMoveRow(
        id=_to_str(row["id"]),
        product_id=_to_str(row["product_id"]),
        from_location_id=_to_optional_str(row["from_location_id"]),
        to_location_id=_to_optional_str(row["to_location_id"]),
        move_type=_to_str(row["move_type"]),
        qty=_to_float(row["qty"], "qty"),
        occurred_at=row["occurred_at"],
        reason_code=_to_optional_str(row["reason_code"]),
        reported_qty=(
            _to_float(row["reported_qty"], "reported_qty")
            if row["reported_qty"] is not None
            else None
        ),
        actual_qty=(
            _to_float(row["actual_qty"], "actual_qty") if row["actual_qty"] is not None else None
        ),
    )


def _observation_for_move_from_row(row: Any) -> ObservationForMove:
    return ObservationForMove(
        id=_to_str(row["id"]),
        observed_at=row["observed_at"],
        product_id=_to_str(row["product_id"]),
        location_id=_to_str(row["location_id"]),
        obs_type=_to_str(row["obs_type"]),
        observed_qty=(
            _to_float(row["observed_qty"], "observed_qty")
            if row["observed_qty"] is not None
            else None
        ),
        confidence=_to_float(row["confidence"], "confidence"),
    )


def list_inventory_moves(
    warehouse_id: str | None = None,
    product_id: str | None = None,
    move_type: str | None = None,
    from_ts: datetime | None = None,
    to_ts: datetime | None = None,
    limit: int = 50,
    offset: int = 0,
) -> ToolResult[ListInventoryMovesResponse]:
    """
    USE THIS TOOL to inspect historical inventory moves with optional warehouse, product,
    move type, and time-window filters.
    """
    try:
        request = ListInventoryMovesRequest(
            warehouse_id=warehouse_id,
            product_id=product_id,
            move_type=move_type,
            from_ts=from_ts,
            to_ts=to_ts,
            limit=limit,
            offset=offset,
        )

        with get_session() as session:
            rows = fetch_inventory_move_rows(session, request)

        moves = [_inventory_move_from_row(row) for row in rows]
        response = ListInventoryMovesResponse(moves=moves)

        return ToolResult(
            data=response,
            message=(
                "No inventory moves matched filters."
                if not response.moves
                else f"Retrieved {len(response.moves)} inventory moves."
            ),
            meta={
                "count": len(response.moves),
                "filters": {
                    "warehouse_id": warehouse_id,
                    "product_id": product_id,
                    "move_type": move_type,
                    "from_ts": from_ts.isoformat() if from_ts else None,
                    "to_ts": to_ts.isoformat() if to_ts else None,
                },
                "pagination": {"limit": limit, "offset": offset},
            },
        )
    except Exception as exc:
        raise RuntimeError("Unable to list inventory moves.") from exc


def get_inventory_move(
    move_id: str,
) -> ToolResult[GetInventoryMoveResponse]:
    """
    USE THIS TOOL to retrieve a single inventory move by its UUID.
    """
    try:
        request = GetInventoryMoveRequest(move_id=move_id)

        with get_session() as session:
            row = fetch_inventory_move_row(session, request)

        if row is None:
            raise ValueError(f"Inventory move not found: {move_id}")

        move = _inventory_move_from_row(row)
        response = GetInventoryMoveResponse(move=move)

        return ToolResult(
            data=response,
            message="Retrieved inventory move details.",
            meta={"move_id": move_id},
        )
    except Exception as exc:
        raise RuntimeError("Unable to get inventory move.") from exc


def get_inventory_move_audit_trace(
    move_id: str,
) -> ToolResult[GetInventoryMoveAuditTraceResponse]:
    """
    USE THIS TOOL to inspect an inventory move together with related sensor observations.
    """
    try:
        request = GetInventoryMoveAuditTraceRequest(move_id=move_id)

        with get_session() as session:
            move_row, observation_rows = fetch_inventory_move_audit_trace_rows(session, request)

        if move_row is None:
            raise ValueError(f"Inventory move not found for audit trace: {move_id}")

        move = _inventory_move_from_row(move_row)
        observations = [_observation_for_move_from_row(row) for row in observation_rows]

        response = GetInventoryMoveAuditTraceResponse(move=move, observations=observations)

        return ToolResult(
            data=response,
            message=(
                "No observations linked to inventory move."
                if not observations
                else f"Retrieved {len(observations)} observations for inventory move."
            ),
            meta={
                "move_id": move_id,
                "observation_count": len(observations),
            },
        )
    except Exception as exc:
        raise RuntimeError("Unable to get inventory move audit trace.") from exc


def get_inventory_adjustments_summary(
    warehouse_id: str | None = None,
    product_id: str | None = None,
    from_ts: datetime | None = None,
    to_ts: datetime | None = None,
) -> ToolResult[GetInventoryAdjustmentsSummaryResponse]:
    """
    USE THIS TOOL to summarize inventory adjustments over a time window, including
    total adjustment count, total quantity, and breakdown by reason code.
    """
    try:
        request = GetInventoryAdjustmentsSummaryRequest(
            warehouse_id=warehouse_id,
            product_id=product_id,
            from_ts=from_ts,
            to_ts=to_ts,
        )

        with get_session() as session:
            summary_row, breakdown_rows = fetch_inventory_adjustments_summary(session, request)

        count = _to_int(summary_row["count"], "count")
        total_qty = _to_float(summary_row["total_qty"], "total_qty")

        by_reason = [
            InventoryAdjustmentByReason(
                reason_code=_to_optional_str(row["reason_code"]),
                count=_to_int(row["count"], "count"),
                total_qty=_to_float(row["total_qty"], "total_qty"),
            )
            for row in breakdown_rows
        ]

        response = GetInventoryAdjustmentsSummaryResponse(
            count=count,
            total_qty=total_qty,
            by_reason=by_reason,
        )

        message = (
            "No inventory adjustments matched filters."
            if count == 0
            else f"Aggregated {count} inventory adjustments."
        )

        return ToolResult(
            data=response,
            message=message,
            meta={
                "filters": {
                    "warehouse_id": warehouse_id,
                    "product_id": product_id,
                    "from_ts": from_ts.isoformat() if from_ts else None,
                    "to_ts": to_ts.isoformat() if to_ts else None,
                },
                "reason_breakdown_count": len(by_reason),
            },
        )
    except Exception as exc:
        raise RuntimeError("Unable to get inventory adjustments summary.") from exc
