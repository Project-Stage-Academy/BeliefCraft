from __future__ import annotations

from typing import Any

from common.schemas.common import ToolResult
from common.schemas.observed_inventory import (
    GetObservedInventorySnapshotRequest,
    ObservedInventoryQualityStatus,
    ObservedInventorySnapshotDevRow,
    ObservedInventorySnapshotRow,
)
from pydantic import TypeAdapter

from ..db.session import get_session
from ..repo.observed_inventory import fetch_observed_inventory_snapshot_rows

_QUALITY_STATUS_LIST_ADAPTER = TypeAdapter(list[ObservedInventoryQualityStatus])


def _to_float(value: Any, field_name: str) -> float:
    if value is None:
        raise ValueError(f"Unexpected null value for {field_name}.")
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid numeric value for {field_name}: {value!r}") from exc


def _to_optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _to_quality_status(
    value: Any,
    field_name: str = "quality_status",
) -> ObservedInventoryQualityStatus:
    if value is None:
        raise ValueError(f"Unexpected null value for {field_name}.")

    if hasattr(value, "value"):
        raw = str(value.value)
    elif hasattr(value, "name"):
        raw = str(value.name).lower()
    else:
        raw = str(value)
        if "." in raw:
            raw = raw.rsplit(".", 1)[-1]
        raw = raw.lower()

    try:
        return ObservedInventoryQualityStatus(raw)
    except ValueError as exc:
        raise ValueError(f"Invalid quality status for {field_name}: {value!r}") from exc


def _snapshot_row_from_row(row: Any) -> ObservedInventorySnapshotRow:
    return ObservedInventorySnapshotRow(
        product_id=row["product_id"],
        location_id=row["location_id"],
        observed_qty=_to_optional_float(row["observed_qty"]),
        confidence=_to_optional_float(row["confidence"]),
        device_id=row["device_id"],
        quality_status=_to_quality_status(row["quality_status"]),
    )


def _snapshot_dev_row_from_row(row: Any) -> ObservedInventorySnapshotDevRow:
    return ObservedInventorySnapshotDevRow(
        product_id=row["product_id"],
        location_id=row["location_id"],
        observed_qty=_to_optional_float(row["observed_qty"]),
        confidence=_to_optional_float(row["confidence"]),
        device_id=row["device_id"],
        quality_status=_to_quality_status(row["quality_status"]),
        on_hand=_to_float(row["on_hand"], "on_hand"),
        reserved=_to_float(row["reserved"], "reserved"),
    )


def _parse_quality_status_in(
    quality_status_in: list[str] | list[ObservedInventoryQualityStatus] | None,
) -> list[ObservedInventoryQualityStatus] | None:
    if quality_status_in is None:
        return None
    return _QUALITY_STATUS_LIST_ADAPTER.validate_python(quality_status_in)


def get_observed_inventory_snapshot(
    quality_status_in: list[str] | list[ObservedInventoryQualityStatus] | None = None,
    dev_mode: bool = False,
) -> ToolResult[list[ObservedInventorySnapshotRow | ObservedInventorySnapshotDevRow]]:
    """
    USE THIS TOOL to retrieve the latest observed inventory snapshot per product/location.

    Set `dev_mode=True` to include ground-truth fields (`on_hand`, `reserved`) for diagnostics.
    """
    try:
        parsed_quality_status_in = _parse_quality_status_in(quality_status_in)
        request = GetObservedInventorySnapshotRequest(
            quality_status_in=parsed_quality_status_in,
            dev_mode=dev_mode,
        )

        with get_session() as session:
            rows = fetch_observed_inventory_snapshot_rows(session, request)

        if request.dev_mode:
            data: list[ObservedInventorySnapshotRow | ObservedInventorySnapshotDevRow] = [
                _snapshot_dev_row_from_row(row)
                for row in rows
            ]
        else:
            data = [_snapshot_row_from_row(row) for row in rows]

        return ToolResult(
            data=data,
            message=(
                "No observed inventory rows matched filters."
                if not data
                else f"Retrieved {len(data)} observed inventory rows."
            ),
            meta={
                "count": len(data),
                "filters": {
                    "quality_status_in": (
                        [status.value for status in request.quality_status_in]
                        if request.quality_status_in
                        else None
                    ),
                    "dev_mode": request.dev_mode,
                },
            },
        )
    except Exception as exc:
        raise RuntimeError("Unable to get observed inventory snapshot.") from exc
