from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from common.schemas.procurement import POStatus, ProcurementGroupBy
from environment_api.smart_query_builder.tools import (
    get_procurement_pipeline_summary,
    get_purchase_order,
    get_supplier,
    list_po_lines,
    list_purchase_orders,
    list_suppliers,
)
from fastapi import APIRouter, Query

from .common import execute_tool

router = APIRouter(prefix="/procurement", tags=["smart-query"])


@router.get("/suppliers")
def procurement_list_suppliers(
    region: str | None = None,
    reliability_min: float | None = Query(default=None, ge=0.0, le=1.0),
    reliability_max: float | None = Query(default=None, ge=0.0, le=1.0),
    name_like: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    return execute_tool(
        lambda: list_suppliers(
            region=region,
            reliability_min=reliability_min,
            reliability_max=reliability_max,
            name_like=name_like,
            limit=limit,
            offset=offset,
        )
    )


@router.get("/suppliers/{supplier_id}")
def procurement_get_supplier(supplier_id: str) -> dict[str, Any]:
    return execute_tool(lambda: get_supplier(supplier_id=supplier_id))


@router.get("/purchase-orders")
def procurement_list_purchase_orders(
    supplier_id: str | None = None,
    destination_warehouse_id: str | None = None,
    status_in: Annotated[list[POStatus] | None, Query()] = None,
    created_after: datetime | None = None,
    created_before: datetime | None = None,
    expected_after: datetime | None = None,
    expected_before: datetime | None = None,
    include_names: bool = False,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    return execute_tool(
        lambda: list_purchase_orders(
            supplier_id=supplier_id,
            destination_warehouse_id=destination_warehouse_id,
            status_in=[s.value for s in status_in] if status_in else None,
            created_after=created_after,
            created_before=created_before,
            expected_after=expected_after,
            expected_before=expected_before,
            include_names=include_names,
            limit=limit,
            offset=offset,
        )
    )


@router.get("/purchase-orders/{purchase_order_id}")
def procurement_get_purchase_order(
    purchase_order_id: str,
    include_names: bool = False,
) -> dict[str, Any]:
    return execute_tool(
        lambda: get_purchase_order(
            purchase_order_id=purchase_order_id,
            include_names=include_names,
        )
    )


@router.get("/po-lines")
def procurement_list_po_lines(
    purchase_order_id: str | None = None,
    purchase_order_ids: Annotated[list[str] | None, Query()] = None,
    product_id: str | None = None,
    include_product_fields: bool = False,
) -> dict[str, Any]:
    return execute_tool(
        lambda: list_po_lines(
            purchase_order_id=purchase_order_id,
            purchase_order_ids=purchase_order_ids,
            product_id=product_id,
            include_product_fields=include_product_fields,
        )
    )


@router.get("/pipeline-summary")
def procurement_pipeline_summary(
    destination_warehouse_id: str | None = None,
    supplier_id: str | None = None,
    status_in: Annotated[list[POStatus] | None, Query()] = None,
    horizon_days: Annotated[int | None, Query(ge=1, le=365)] = None,
    group_by: ProcurementGroupBy = ProcurementGroupBy.warehouse_supplier,
    include_names: bool = False,
) -> dict[str, Any]:
    return execute_tool(
        lambda: get_procurement_pipeline_summary(
            destination_warehouse_id=destination_warehouse_id,
            supplier_id=supplier_id,
            status_in=[s.value for s in status_in] if status_in else None,
            horizon_days=horizon_days,
            group_by=group_by.value,
            include_names=include_names,
        )
    )
