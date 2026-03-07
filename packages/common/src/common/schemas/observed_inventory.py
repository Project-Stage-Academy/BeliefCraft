from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ObservedInventoryQualityStatus(StrEnum):
    OK = "ok"
    DAMAGED = "damaged"
    EXPIRED = "expired"
    QUARANTINE = "quarantine"


class GetObservedInventorySnapshotRequest(BaseModel):
    quality_status_in: list[ObservedInventoryQualityStatus] | None = None
    dev_mode: bool = False

    model_config = ConfigDict(extra="forbid")


class ObservedInventorySnapshotRow(BaseModel):
    product_id: UUID
    location_id: UUID
    observed_qty: float | None
    confidence: float | None
    device_id: UUID
    quality_status: ObservedInventoryQualityStatus

    model_config = ConfigDict(extra="forbid")


class ObservedInventorySnapshotDevRow(ObservedInventorySnapshotRow):
    on_hand: float
    reserved: float

