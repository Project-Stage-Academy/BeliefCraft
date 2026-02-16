from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from .common import Pagination


class GetAtRiskOrdersRequest(Pagination):
    """
    Request contract for at-risk orders query.
    """

    horizon_hours: int = Field(default=48, ge=1, le=24 * 30)
    min_sla_priority: float = Field(default=0.7, ge=0.0, le=1.0)
    status: str | None = None

    model_config = ConfigDict(extra="forbid")


class AtRiskOrderRow(BaseModel):
    """
    Row contract for at-risk order analytics output.
    """

    order_id: str
    status: str
    promised_at: datetime
    sla_priority: float
    total_lines: int
    total_open_qty: float
    total_penalty_exposure: float
    top_missing_skus: list[str]

    model_config = ConfigDict(extra="forbid")
