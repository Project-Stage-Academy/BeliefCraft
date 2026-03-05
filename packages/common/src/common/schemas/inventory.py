from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

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


class ListInventoryMovesRequest(Pagination):
    """
    Request contract for listing inventory moves with optional filters.
    """

    warehouse_id: str | None = None
    product_id: str | None = None
    move_type: str | None = None
    from_ts: datetime | None = None
    to_ts: datetime | None = None

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_date_range(self) -> ListInventoryMovesRequest:
        if self.from_ts and self.to_ts and self.from_ts > self.to_ts:
            raise ValueError("from_ts must be less than or equal to to_ts")
        return self


class InventoryMoveRow(BaseModel):
    """
    Row contract for inventory move history.
    """

    id: str
    product_id: str
    from_location_id: str | None = None
    to_location_id: str | None = None
    move_type: str
    qty: float = Field(gt=0)
    occurred_at: datetime
    reason_code: str | None = None
    reported_qty: float | None = Field(default=None, ge=0)
    actual_qty: float | None = Field(default=None, ge=0)

    model_config = ConfigDict(extra="forbid")


class ListInventoryMovesResponse(BaseModel):
    moves: list[InventoryMoveRow]

    model_config = ConfigDict(extra="forbid")


class GetInventoryMoveRequest(BaseModel):
    move_id: str

    model_config = ConfigDict(extra="forbid")


class GetInventoryMoveResponse(BaseModel):
    move: InventoryMoveRow

    model_config = ConfigDict(extra="forbid")


class ObservationForMove(BaseModel):
    """
    Observation row related to a specific inventory move.
    """

    id: str
    observed_at: datetime
    product_id: str
    location_id: str
    obs_type: str
    observed_qty: float | None = None
    confidence: float

    model_config = ConfigDict(extra="forbid")


class GetInventoryMoveAuditTraceRequest(BaseModel):
    move_id: str

    model_config = ConfigDict(extra="forbid")


class GetInventoryMoveAuditTraceResponse(BaseModel):
    move: InventoryMoveRow
    observations: list[ObservationForMove]

    model_config = ConfigDict(extra="forbid")


class InventoryAdjustmentByReason(BaseModel):
    reason_code: str | None = None
    count: int = Field(ge=0)
    total_qty: float = Field(ge=0)

    model_config = ConfigDict(extra="forbid")


class GetInventoryAdjustmentsSummaryRequest(BaseModel):
    warehouse_id: str | None = None
    product_id: str | None = None
    from_ts: datetime | None = None
    to_ts: datetime | None = None

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_date_range(self) -> GetInventoryAdjustmentsSummaryRequest:
        if self.from_ts and self.to_ts and self.from_ts > self.to_ts:
            raise ValueError("from_ts must be less than or equal to to_ts")
        return self


class GetInventoryAdjustmentsSummaryResponse(BaseModel):
    count: int = Field(ge=0)
    total_qty: float = Field(ge=0)
    by_reason: list[InventoryAdjustmentByReason]

    model_config = ConfigDict(extra="forbid")
