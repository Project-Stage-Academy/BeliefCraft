from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from .common import Pagination


class GetCurrentInventoryRequest(Pagination):
    """
    Request contract for current inventory lookup.
    """

    warehouse_id: str | None = None
    location_id: str | None = None
    sku: str | None = None
    product_id: str | None = None
    include_reserved: bool = True

    model_config = ConfigDict(extra="forbid")


class CurrentInventoryRow(BaseModel):
    """
    Row contract for inventory snapshot results.
    """

    warehouse_id: str
    location_id: str
    location_code: str
    product_id: str
    sku: str
    on_hand: float
    reserved: float
    available: float
    quality_status: str | None = None
    last_count_at: datetime | None = None

    model_config = ConfigDict(extra="forbid")
