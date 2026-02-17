from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class GetShipmentsDelaySummaryRequest(BaseModel):
    """
    Request contract for shipment delay analytics.
    """

    date_from: datetime
    date_to: datetime
    warehouse_id: str | None = None
    route_id: str | None = None
    status: str | None = None

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_date_range(self) -> GetShipmentsDelaySummaryRequest:
        if self.date_to < self.date_from:
            raise ValueError("date_to must be greater than or equal to date_from")
        return self


class DelayedShipmentRow(BaseModel):
    """
    Row contract for delayed shipment details.
    """

    shipment_id: str
    status: str | None = None
    route_id: str | None = None
    origin_warehouse_id: str | None = None
    destination_warehouse_id: str | None = None
    shipped_at: datetime | None = None
    arrived_at: datetime | None = None
    transit_hours: float | None = None
    delayed_reason: str

    model_config = ConfigDict(extra="forbid")


class ShipmentsDelaySummary(BaseModel):
    """
    Aggregate payload for shipment delay summary.
    """

    total_shipments: int = Field(ge=0)
    delivered_count: int = Field(ge=0)
    in_transit_count: int = Field(ge=0)
    delayed_count: int = Field(ge=0)
    avg_transit_hours: float | None = None
    delayed_shipments: list[DelayedShipmentRow] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")
