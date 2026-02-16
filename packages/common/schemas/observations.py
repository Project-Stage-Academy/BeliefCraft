from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, model_validator

from .common import Pagination


class CompareObservationsToBalancesRequest(Pagination):
    """
    Request contract for observations vs balances comparison.
    """

    warehouse_id: str | None = None
    location_id: str | None = None
    sku: str | None = None
    product_id: str | None = None
    observed_from: datetime
    observed_to: datetime

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_date_range(self) -> CompareObservationsToBalancesRequest:
        if self.observed_to < self.observed_from:
            raise ValueError("observed_to must be greater than or equal to observed_from")
        return self


class ObservationBalanceComparisonRow(BaseModel):
    """
    Row contract for noisy observation and inventory balance comparison.
    """

    warehouse_id: str
    location_id: str
    sku: str
    product_id: str
    observed_estimate: float
    on_hand: float
    reserved: float
    available: float
    discrepancy: float
    obs_count: int
    avg_confidence: float | None = None

    model_config = ConfigDict(extra="forbid")
