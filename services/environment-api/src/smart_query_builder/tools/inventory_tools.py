from __future__ import annotations

from typing import Any

from schemas.common import ToolResult
from schemas.inventory import CurrentInventoryRow, GetCurrentInventoryRequest

from ..db.session import get_session
from ..repo.inventory import fetch_current_inventory_rows


def _to_float(value: Any) -> float:
    return float(value) if value is not None else 0.0


def _to_str(value: Any) -> str:
    return "" if value is None else str(value)


def get_current_inventory(
    warehouse_id: str | None = None,
    location_id: str | None = None,
    sku: str | None = None,
    product_id: str | None = None,
    include_reserved: bool = True,
    limit: int = 50,
    offset: int = 0,
) -> ToolResult[list[CurrentInventoryRow]]:
    """
    USE THIS TOOL whenever you need current inventory by warehouse or location,
    especially to surface low-stock SKUs first.

    Filters support warehouse/location scope with optional SKU/product narrowing.
    Results are sorted by available quantity ascending, then SKU.
    """
    try:
        request = GetCurrentInventoryRequest(
            warehouse_id=warehouse_id,
            location_id=location_id,
            sku=sku,
            product_id=product_id,
            include_reserved=include_reserved,
            limit=limit,
            offset=offset,
        )

        with get_session() as session:
            rows = fetch_current_inventory_rows(session, request)

        if not rows:
            return ToolResult(
                data=[],
                message="No results for current inventory.",
                meta={
                    "count": 0,
                    "filters": {
                        "warehouse_id": warehouse_id,
                        "location_id": location_id,
                        "sku": sku,
                        "product_id": product_id,
                        "include_reserved": include_reserved,
                    },
                    "pagination": {"limit": limit, "offset": offset},
                },
            )

        data = [
            CurrentInventoryRow(
                warehouse_id=_to_str(row["warehouse_id"]),
                location_id=_to_str(row["location_id"]),
                location_code=_to_str(row["location_code"]),
                product_id=_to_str(row["product_id"]),
                sku=_to_str(row["sku"]),
                on_hand=_to_float(row["on_hand"]),
                reserved=_to_float(row["reserved"]),
                available=_to_float(row["available"]),
                quality_status=(
                    str(row["quality_status"]) if row["quality_status"] is not None else None
                ),
                last_count_at=row["last_count_at"],
            )
            for row in rows
        ]

        return ToolResult(
            data=data,
            message=f"Retrieved {len(data)} current inventory rows.",
            meta={
                "count": len(data),
                "filters": {
                    "warehouse_id": warehouse_id,
                    "location_id": location_id,
                    "sku": sku,
                    "product_id": product_id,
                    "include_reserved": include_reserved,
                },
                "pagination": {"limit": limit, "offset": offset},
            },
        )
    except Exception:
        raise RuntimeError("Unable to fetch current inventory.") from None
