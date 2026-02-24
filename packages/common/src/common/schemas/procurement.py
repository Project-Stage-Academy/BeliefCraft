from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .common import Pagination


class POStatus(StrEnum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    PARTIAL = "partial"
    RECEIVED = "received"
    CLOSED = "closed"


class ProcurementPagination(Pagination):
    limit: int = Field(default=100, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)

    model_config = ConfigDict(extra="forbid")


class SupplierOut(BaseModel):
    id: UUID
    name: str
    reliability_score: float = Field(ge=0, le=1)
    region: str

    model_config = ConfigDict(extra="forbid")


class ListSuppliersRequest(ProcurementPagination):
    region: str | None = None
    reliability_min: float | None = Field(default=None, ge=0, le=1)
    reliability_max: float | None = Field(default=None, ge=0, le=1)
    name_like: str | None = None
    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_reliability_range(self) -> ListSuppliersRequest:
        if (
            self.reliability_min is not None
            and self.reliability_max is not None
            and self.reliability_min > self.reliability_max
        ):
            raise ValueError("reliability_min must be less than or equal to reliability_max")
        return self


class ListSuppliersResponse(BaseModel):
    suppliers: list[SupplierOut]

    model_config = ConfigDict(extra="forbid")


class GetSupplierRequest(BaseModel):
    supplier_id: UUID

    model_config = ConfigDict(extra="forbid")


class GetSupplierResponse(BaseModel):
    supplier: SupplierOut

    model_config = ConfigDict(extra="forbid")


class PurchaseOrderOut(BaseModel):
    id: UUID
    supplier_id: UUID
    destination_warehouse_id: UUID
    status: POStatus
    expected_at: datetime | None = None
    leadtime_model_id: UUID | None = None
    created_at: datetime
    supplier_name: str | None = None
    warehouse_name: str | None = None

    model_config = ConfigDict(extra="forbid")


class ListPurchaseOrdersRequest(ProcurementPagination):
    supplier_id: UUID | None = None
    destination_warehouse_id: UUID | None = None
    status_in: list[POStatus] | None = None
    created_after: datetime | None = None
    created_before: datetime | None = None
    expected_after: datetime | None = None
    expected_before: datetime | None = None
    include_names: bool = False
    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_date_ranges(self) -> ListPurchaseOrdersRequest:
        if self.created_after and self.created_before and self.created_after > self.created_before:
            raise ValueError("created_after must be less than or equal to created_before")
        if (
            self.expected_after
            and self.expected_before
            and self.expected_after > self.expected_before
        ):
            raise ValueError("expected_after must be less than or equal to expected_before")
        return self


class ListPurchaseOrdersResponse(BaseModel):
    purchase_orders: list[PurchaseOrderOut]

    model_config = ConfigDict(extra="forbid")


class GetPurchaseOrderRequest(BaseModel):
    purchase_order_id: UUID
    include_names: bool = False

    model_config = ConfigDict(extra="forbid")


class GetPurchaseOrderResponse(BaseModel):
    purchase_order: PurchaseOrderOut

    model_config = ConfigDict(extra="forbid")


class PoLineOut(BaseModel):
    id: UUID
    purchase_order_id: UUID
    product_id: UUID
    qty_ordered: float = Field(gt=0)
    qty_received: float = Field(ge=0)
    remaining_qty: float = Field(ge=0)
    sku: str | None = None
    product_name: str | None = None
    category: str | None = None

    model_config = ConfigDict(extra="forbid")


class ListPoLinesRequest(BaseModel):
    purchase_order_id: UUID | None = None
    purchase_order_ids: list[UUID] | None = None
    product_id: UUID | None = None
    include_product_fields: bool = False

    model_config = ConfigDict(extra="forbid")


class ListPoLinesResponse(BaseModel):
    po_lines: list[PoLineOut]

    model_config = ConfigDict(extra="forbid")


class ProcurementGroupBy(StrEnum):
    warehouse = "warehouse"
    supplier = "supplier"
    warehouse_supplier = "warehouse_supplier"


class ProcurementPipelineRow(BaseModel):
    destination_warehouse_id: UUID | None = None
    supplier_id: UUID | None = None
    po_count: int = Field(ge=0)
    total_qty_ordered: float = Field(ge=0)
    total_qty_received: float = Field(ge=0)
    total_qty_remaining: float = Field(ge=0)
    next_expected_at: datetime | None = None
    last_created_at: datetime | None = None
    supplier_name: str | None = None
    warehouse_name: str | None = None

    model_config = ConfigDict(extra="forbid")


class ProcurementPipelineSummaryRequest(BaseModel):
    destination_warehouse_id: UUID | None = None
    supplier_id: UUID | None = None
    status_in: list[POStatus] | None = None
    horizon_days: int | None = Field(default=None, ge=1, le=365)
    group_by: ProcurementGroupBy = ProcurementGroupBy.warehouse_supplier
    include_names: bool = False

    model_config = ConfigDict(extra="forbid")


class ProcurementPipelineSummaryResponse(BaseModel):
    rows: list[ProcurementPipelineRow]

    model_config = ConfigDict(extra="forbid")
