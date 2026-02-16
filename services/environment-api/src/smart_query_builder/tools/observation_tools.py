from __future__ import annotations

from datetime import datetime
from typing import Any

from schemas.common import ToolResult
from schemas.observations import (
    CompareObservationsToBalancesRequest,
    ObservationBalanceComparisonRow,
)

from ..db.session import get_session
from ..repo.observations import fetch_observation_vs_balance_rows


def _to_float(value: Any) -> float:
    return float(value) if value is not None else 0.0


def _to_str(value: Any) -> str:
    return "" if value is None else str(value)


def compare_observations_to_balances(
    observed_from: datetime,
    observed_to: datetime,
    warehouse_id: str | None = None,
    location_id: str | None = None,
    sku: str | None = None,
    product_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> ToolResult[list[ObservationBalanceComparisonRow]]:
    """
    USE THIS TOOL whenever you need to compare noisy observed quantities against
    inventory balances and prioritize the biggest discrepancies.

    This tool returns weighted observation estimates, current balances, and discrepancy metrics.
    """
    try:
        request = CompareObservationsToBalancesRequest(
            warehouse_id=warehouse_id,
            location_id=location_id,
            sku=sku,
            product_id=product_id,
            observed_from=observed_from,
            observed_to=observed_to,
            limit=limit,
            offset=offset,
        )

        with get_session() as session:
            rows = fetch_observation_vs_balance_rows(session, request)

        if not rows:
            return ToolResult(
                data=[],
                message="No results for observations vs balances.",
                meta={
                    "count": 0,
                    "filters": {
                        "warehouse_id": warehouse_id,
                        "location_id": location_id,
                        "sku": sku,
                        "product_id": product_id,
                        "observed_from": observed_from.isoformat(),
                        "observed_to": observed_to.isoformat(),
                    },
                    "pagination": {"limit": limit, "offset": offset},
                },
            )

        data = [
            ObservationBalanceComparisonRow(
                warehouse_id=_to_str(row["warehouse_id"]),
                location_id=_to_str(row["location_id"]),
                sku=_to_str(row["sku"]),
                product_id=_to_str(row["product_id"]),
                observed_estimate=_to_float(row["observed_estimate"]),
                on_hand=_to_float(row["on_hand"]),
                reserved=_to_float(row["reserved"]),
                available=_to_float(row["available"]),
                discrepancy=_to_float(row["discrepancy"]),
                obs_count=int(row["obs_count"] or 0),
                avg_confidence=(
                    float(row["avg_confidence"]) if row["avg_confidence"] is not None else None
                ),
            )
            for row in rows
        ]

        return ToolResult(
            data=data,
            message=f"Retrieved {len(data)} observation comparison rows.",
            meta={
                "count": len(data),
                "filters": {
                    "warehouse_id": warehouse_id,
                    "location_id": location_id,
                    "sku": sku,
                    "product_id": product_id,
                    "observed_from": observed_from.isoformat(),
                    "observed_to": observed_to.isoformat(),
                },
                "pagination": {"limit": limit, "offset": offset},
            },
        )
    except Exception:
        raise RuntimeError("Unable to compare observations to balances.") from None
