from __future__ import annotations

from typing import Any

from common.schemas import AtRiskOrderRow, GetAtRiskOrdersRequest
from common.schemas.common import ToolResult

from ..db.session import get_session
from ..repo.orders import fetch_at_risk_order_rows


def _to_float(value: Any) -> float:
    return float(value) if value is not None else 0.0


def _to_str(value: Any) -> str:
    return "" if value is None else str(value)


def get_at_risk_orders(
    horizon_hours: int = 48,
    min_sla_priority: float = 0.7,
    status: str | None = None,
    top_missing_skus_limit: int = 5,
    limit: int = 50,
    offset: int = 0,
) -> ToolResult[list[AtRiskOrderRow]]:
    """
    USE THIS TOOL whenever you need to identify orders with near-term promise risk,
    unresolved quantities, and highest penalty exposure.

    It ranks at-risk orders by potential penalty impact and urgency.
    """
    try:
        request = GetAtRiskOrdersRequest(
            horizon_hours=horizon_hours,
            min_sla_priority=min_sla_priority,
            status=status,
            top_missing_skus_limit=top_missing_skus_limit,
            limit=limit,
            offset=offset,
        )

        with get_session() as session:
            rows = fetch_at_risk_order_rows(session, request)

        if not rows:
            return ToolResult(
                data=[],
                message="No results for at-risk orders.",
                meta={
                    "count": 0,
                    "filters": {
                        "horizon_hours": horizon_hours,
                        "min_sla_priority": min_sla_priority,
                        "status": status,
                        "top_missing_skus_limit": top_missing_skus_limit,
                    },
                    "pagination": {"limit": limit, "offset": offset},
                },
            )

        data: list[AtRiskOrderRow] = []
        for row in rows:
            top_missing_skus = [str(sku) for sku in (row["top_missing_skus"] or [])][
                : request.top_missing_skus_limit
            ]
            data.append(
                AtRiskOrderRow(
                    order_id=_to_str(row["order_id"]),
                    status=_to_str(row["status"]),
                    promised_at=row["promised_at"],
                    sla_priority=_to_float(row["sla_priority"]),
                    total_lines=int(row["total_lines"] or 0),
                    total_open_qty=_to_float(row["total_open_qty"]),
                    total_penalty_exposure=_to_float(row["total_penalty_exposure"]),
                    top_missing_skus=top_missing_skus,
                )
            )

        return ToolResult(
            data=data,
            message=f"Retrieved {len(data)} at-risk orders.",
            meta={
                "count": len(data),
                "filters": {
                    "horizon_hours": horizon_hours,
                    "min_sla_priority": min_sla_priority,
                    "status": status,
                    "top_missing_skus_limit": top_missing_skus_limit,
                },
                "pagination": {"limit": limit, "offset": offset},
            },
        )
    except Exception as exc:
        raise RuntimeError("Unable to fetch at-risk orders.") from exc
