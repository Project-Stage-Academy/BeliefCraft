from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .common import Pagination


class TopologyLocationType(StrEnum):
    SHELF = "shelf"
    BIN = "bin"
    PALLET_POS = "pallet_pos"
    DOCK = "dock"
    VIRTUAL = "virtual"


class TopologyPagination(Pagination):
    limit: int = Field(default=50, ge=1, le=500)
    offset: int = Field(default=0, ge=0)

    model_config = ConfigDict(extra="forbid")


class WarehouseOut(BaseModel):
    id: UUID
    name: str
    region: str
    tz: str

    model_config = ConfigDict(extra="forbid")


class ListWarehousesRequest(TopologyPagination):
    region: str | None = None
    name_like: str | None = None

    model_config = ConfigDict(extra="forbid")


class ListWarehousesResponse(BaseModel):
    warehouses: list[WarehouseOut]

    model_config = ConfigDict(extra="forbid")


class GetWarehouseRequest(BaseModel):
    warehouse_id: UUID

    model_config = ConfigDict(extra="forbid")


class GetWarehouseResponse(BaseModel):
    warehouse: WarehouseOut

    model_config = ConfigDict(extra="forbid")


class LocationOut(BaseModel):
    id: UUID
    warehouse_id: UUID
    parent_location_id: UUID | None = None
    code: str
    type: TopologyLocationType
    capacity_units: int = Field(ge=0)

    model_config = ConfigDict(extra="forbid")


class ListLocationsRequest(TopologyPagination):
    warehouse_id: UUID | None = None
    parent_location_id: UUID | None = None
    type: TopologyLocationType | None = None
    code_like: str | None = None

    model_config = ConfigDict(extra="forbid")


class ListLocationsResponse(BaseModel):
    locations: list[LocationOut]

    model_config = ConfigDict(extra="forbid")


class GetLocationRequest(BaseModel):
    location_id: UUID

    model_config = ConfigDict(extra="forbid")


class GetLocationResponse(BaseModel):
    location: LocationOut

    model_config = ConfigDict(extra="forbid")


class LocationTreeNode(BaseModel):
    id: UUID
    warehouse_id: UUID
    parent_location_id: UUID | None = None
    code: str
    type: TopologyLocationType
    capacity_units: int = Field(ge=0)
    children: list[LocationTreeNode] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class GetWarehouseLocationsTreeRequest(BaseModel):
    warehouse_id: UUID

    model_config = ConfigDict(extra="forbid")


class GetWarehouseLocationsTreeResponse(BaseModel):
    warehouse_id: UUID
    warehouse_name: str
    roots: list[LocationTreeNode]
    node_count: int = Field(ge=0)
    root_count: int = Field(ge=0)

    model_config = ConfigDict(extra="forbid")


class LocationCapacityUtilizationRow(BaseModel):
    location_id: UUID
    capacity_units: int = Field(ge=0)
    observed_qty_sum: float | None = Field(default=None, ge=0)
    utilization_estimate: float | None = Field(default=None, ge=0)
    confidence_avg: float | None = Field(default=None, ge=0, le=1)
    obs_count: int = Field(ge=0)

    model_config = ConfigDict(extra="forbid")


class GetWarehouseCapacityUtilizationRequest(BaseModel):
    warehouse_id: UUID
    snapshot_at: datetime | None = None
    observed_from: datetime | None = None
    observed_to: datetime | None = None
    lookback_hours: int = Field(default=24, ge=1, le=24 * 30)
    type: TopologyLocationType | None = None

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_time_window(self) -> GetWarehouseCapacityUtilizationRequest:
        uses_snapshot = self.snapshot_at is not None
        uses_range = self.observed_from is not None or self.observed_to is not None

        if uses_snapshot and uses_range:
            raise ValueError(
                "Use either snapshot_at or observed_from/observed_to, not both."
            )

        if not uses_snapshot and (
            self.observed_from is None or self.observed_to is None
        ):
            raise ValueError(
                "Provide snapshot_at, or provide both observed_from and observed_to."
            )

        if (
            self.observed_from is not None
            and self.observed_to is not None
            and self.observed_from > self.observed_to
        ):
            raise ValueError("observed_from must be less than or equal to observed_to")

        return self


class GetWarehouseCapacityUtilizationResponse(BaseModel):
    warehouse_id: UUID
    warehouse_name: str
    location_count: int = Field(ge=0)
    total_capacity_units: int = Field(ge=0)
    total_observed_qty_sum: float | None = Field(default=None, ge=0)
    utilization_estimate: float | None = Field(default=None, ge=0)
    rows: list[LocationCapacityUtilizationRow]

    model_config = ConfigDict(extra="forbid")


LocationTreeNode.model_rebuild()



