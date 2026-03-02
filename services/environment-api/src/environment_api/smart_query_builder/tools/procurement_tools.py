from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from common.schemas.common import ToolResult
from common.schemas.procurement import (
    GetPurchaseOrderRequest,
    GetPurchaseOrderResponse,
    GetSupplierRequest,
    GetSupplierResponse,
    ListPoLinesRequest,
    ListPoLinesResponse,
    ListPurchaseOrdersRequest,
    ListPurchaseOrdersResponse,
    ListSuppliersRequest,
    ListSuppliersResponse,
    PoLineOut,
    POStatus,
    ProcurementGroupBy,
    ProcurementPipelineRow,
    ProcurementPipelineSummaryRequest,
    ProcurementPipelineSummaryResponse,
    PurchaseOrderOut,
    SupplierOut,
)

from ..db.session import get_session
from ..repo.procurement import (
    fetch_po_line_rows,
    fetch_procurement_pipeline_summary_rows,
    fetch_purchase_order_row,
    fetch_purchase_order_rows,
    fetch_supplier_row,
    fetch_supplier_rows,
)


def _to_float(value: Any, field_name: str) -> float:
    if value is None:
        raise ValueError(f"Unexpected null value for {field_name}.")
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid numeric value for {field_name}: {value!r}") from exc


def _to_int(value: Any, field_name: str) -> int:
    if value is None:
        raise ValueError(f"Unexpected null value for {field_name}.")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid integer value for {field_name}: {value!r}") from exc


def _to_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(getattr(value, "value", value))


def _to_status(value: Any, field_name: str = "status") -> POStatus:
    raw = _to_optional_str(value)
    if raw is None:
        raise ValueError(f"Unexpected null value for {field_name}.")
    try:
        return POStatus(raw)
    except ValueError:
        return POStatus(raw.lower())


def _parse_uuid(value: str, field_name: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as exc:
        raise ValueError(f"Invalid UUID for {field_name}: {value!r}") from exc


def _parse_optional_uuid(value: str | None, field_name: str) -> UUID | None:
    if value is None:
        return None
    return _parse_uuid(value, field_name)


def _parse_uuid_list(values: list[str] | None, field_name: str) -> list[UUID] | None:
    if values is None:
        return None
    return [_parse_uuid(value, field_name) for value in values]


def _parse_status_list(values: list[str] | None) -> list[POStatus] | None:
    if values is None:
        return None
    return [POStatus(value) for value in values]


def _parse_group_by(value: str) -> ProcurementGroupBy:
    return ProcurementGroupBy(value)


def _serialize_statuses(status_in: list[POStatus] | None) -> list[str] | None:
    if not status_in:
        return None
    return [status.value for status in status_in]


def _supplier_from_row(row: Any) -> SupplierOut:
    return SupplierOut(
        id=row["id"],
        name=str(row["name"]),
        reliability_score=_to_float(row["reliability_score"], "reliability_score"),
        region=str(row["region"]),
    )


def _purchase_order_from_row(row: Any) -> PurchaseOrderOut:
    return PurchaseOrderOut(
        id=row["id"],
        supplier_id=row["supplier_id"],
        destination_warehouse_id=row["destination_warehouse_id"],
        status=_to_status(row["status"]),
        expected_at=row["expected_at"],
        leadtime_model_id=row["leadtime_model_id"],
        created_at=row["created_at"],
        supplier_name=_to_optional_str(row["supplier_name"]),
        warehouse_name=_to_optional_str(row["warehouse_name"]),
    )


def _po_line_from_row(row: Any) -> PoLineOut:
    return PoLineOut(
        id=row["id"],
        purchase_order_id=row["purchase_order_id"],
        product_id=row["product_id"],
        qty_ordered=_to_float(row["qty_ordered"], "qty_ordered"),
        qty_received=_to_float(row["qty_received"], "qty_received"),
        remaining_qty=_to_float(row["remaining_qty"], "remaining_qty"),
        sku=_to_optional_str(row["sku"]),
        product_name=_to_optional_str(row["product_name"]),
        category=_to_optional_str(row["category"]),
    )


def _pipeline_row_from_row(row: Any) -> ProcurementPipelineRow:
    return ProcurementPipelineRow(
        destination_warehouse_id=row["destination_warehouse_id"],
        supplier_id=row["supplier_id"],
        po_count=_to_int(row["po_count"], "po_count"),
        total_qty_ordered=_to_float(row["total_qty_ordered"], "total_qty_ordered"),
        total_qty_received=_to_float(row["total_qty_received"], "total_qty_received"),
        total_qty_remaining=_to_float(row["total_qty_remaining"], "total_qty_remaining"),
        next_expected_at=row["next_expected_at"],
        last_created_at=row["last_created_at"],
        supplier_name=_to_optional_str(row["supplier_name"]),
        warehouse_name=_to_optional_str(row["warehouse_name"]),
    )


def list_suppliers(
    region: str | None = None,
    reliability_min: float | None = None,
    reliability_max: float | None = None,
    name_like: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> ToolResult[ListSuppliersResponse]:
    """
    USE THIS TOOL to query suppliers by region, reliability range, or name match.
    """
    try:
        request = ListSuppliersRequest(
            region=region,
            reliability_min=reliability_min,
            reliability_max=reliability_max,
            name_like=name_like,
            limit=limit,
            offset=offset,
        )

        with get_session() as session:
            rows = fetch_supplier_rows(session, request)

        response = ListSuppliersResponse(suppliers=[_supplier_from_row(row) for row in rows])
        return ToolResult(
            data=response,
            message=(
                "No suppliers matched filters."
                if not response.suppliers
                else f"Retrieved {len(response.suppliers)} suppliers."
            ),
            meta={
                "count": len(response.suppliers),
                "filters": {
                    "region": request.region,
                    "reliability_min": request.reliability_min,
                    "reliability_max": request.reliability_max,
                    "name_like": request.name_like,
                },
                "pagination": {"limit": request.limit, "offset": request.offset},
            },
        )
    except Exception as exc:
        raise RuntimeError("Unable to list suppliers.") from exc


def get_supplier(
    supplier_id: str,
) -> ToolResult[GetSupplierResponse]:
    """
    USE THIS TOOL to retrieve supplier details by supplier UUID.
    """
    try:
        request = GetSupplierRequest(supplier_id=_parse_uuid(supplier_id, "supplier_id"))

        with get_session() as session:
            row = fetch_supplier_row(session, request)

        if row is None:
            raise ValueError(f"Supplier not found: {supplier_id}")

        response = GetSupplierResponse(supplier=_supplier_from_row(row))
        return ToolResult(
            data=response,
            message="Retrieved supplier details.",
            meta={"supplier_id": supplier_id},
        )
    except Exception as exc:
        raise RuntimeError("Unable to get supplier.") from exc


def list_purchase_orders(
    supplier_id: str | None = None,
    destination_warehouse_id: str | None = None,
    status_in: list[str] | None = None,
    created_after: datetime | None = None,
    created_before: datetime | None = None,
    expected_after: datetime | None = None,
    expected_before: datetime | None = None,
    include_names: bool = False,
    limit: int = 100,
    offset: int = 0,
) -> ToolResult[ListPurchaseOrdersResponse]:
    """
    USE THIS TOOL to inspect purchase orders with supplier/warehouse/date/status filters.
    """
    try:
        request = ListPurchaseOrdersRequest(
            supplier_id=_parse_optional_uuid(supplier_id, "supplier_id"),
            destination_warehouse_id=_parse_optional_uuid(
                destination_warehouse_id, "destination_warehouse_id"
            ),
            status_in=_parse_status_list(status_in),
            created_after=created_after,
            created_before=created_before,
            expected_after=expected_after,
            expected_before=expected_before,
            include_names=include_names,
            limit=limit,
            offset=offset,
        )

        with get_session() as session:
            rows = fetch_purchase_order_rows(session, request)

        response = ListPurchaseOrdersResponse(
            purchase_orders=[_purchase_order_from_row(row) for row in rows]
        )
        return ToolResult(
            data=response,
            message=(
                "No purchase orders matched filters."
                if not response.purchase_orders
                else f"Retrieved {len(response.purchase_orders)} purchase orders."
            ),
            meta={
                "count": len(response.purchase_orders),
                "filters": {
                    "supplier_id": str(request.supplier_id) if request.supplier_id else None,
                    "destination_warehouse_id": (
                        str(request.destination_warehouse_id)
                        if request.destination_warehouse_id
                        else None
                    ),
                    "status_in": _serialize_statuses(request.status_in),
                    "created_after": (
                        request.created_after.isoformat() if request.created_after else None
                    ),
                    "created_before": (
                        request.created_before.isoformat() if request.created_before else None
                    ),
                    "expected_after": (
                        request.expected_after.isoformat() if request.expected_after else None
                    ),
                    "expected_before": (
                        request.expected_before.isoformat() if request.expected_before else None
                    ),
                    "include_names": request.include_names,
                },
                "pagination": {"limit": request.limit, "offset": request.offset},
            },
        )
    except Exception as exc:
        raise RuntimeError("Unable to list purchase orders.") from exc


def get_purchase_order(
    purchase_order_id: str,
    include_names: bool = False,
) -> ToolResult[GetPurchaseOrderResponse]:
    """
    USE THIS TOOL to fetch a single purchase order by UUID.
    """
    try:
        request = GetPurchaseOrderRequest(
            purchase_order_id=_parse_uuid(purchase_order_id, "purchase_order_id"),
            include_names=include_names,
        )

        with get_session() as session:
            row = fetch_purchase_order_row(session, request)

        if row is None:
            raise ValueError(f"Purchase order not found: {purchase_order_id}")

        response = GetPurchaseOrderResponse(purchase_order=_purchase_order_from_row(row))
        return ToolResult(
            data=response,
            message="Retrieved purchase order details.",
            meta={
                "purchase_order_id": purchase_order_id,
                "include_names": include_names,
            },
        )
    except Exception as exc:
        raise RuntimeError("Unable to get purchase order.") from exc


def list_po_lines(
    purchase_order_id: str | None = None,
    purchase_order_ids: list[str] | None = None,
    product_id: str | None = None,
    include_product_fields: bool = False,
) -> ToolResult[ListPoLinesResponse]:
    """
    USE THIS TOOL to inspect PO line items and remaining quantities.
    """
    try:
        request = ListPoLinesRequest(
            purchase_order_id=_parse_optional_uuid(purchase_order_id, "purchase_order_id"),
            purchase_order_ids=_parse_uuid_list(purchase_order_ids, "purchase_order_ids"),
            product_id=_parse_optional_uuid(product_id, "product_id"),
            include_product_fields=include_product_fields,
        )

        with get_session() as session:
            rows = fetch_po_line_rows(session, request)

        response = ListPoLinesResponse(po_lines=[_po_line_from_row(row) for row in rows])
        return ToolResult(
            data=response,
            message=(
                "No PO lines matched filters."
                if not response.po_lines
                else f"Retrieved {len(response.po_lines)} PO lines."
            ),
            meta={
                "count": len(response.po_lines),
                "filters": {
                    "purchase_order_id": (
                        str(request.purchase_order_id) if request.purchase_order_id else None
                    ),
                    "purchase_order_ids": (
                        [str(po_id) for po_id in request.purchase_order_ids]
                        if request.purchase_order_ids
                        else None
                    ),
                    "product_id": str(request.product_id) if request.product_id else None,
                    "include_product_fields": request.include_product_fields,
                },
            },
        )
    except Exception as exc:
        raise RuntimeError("Unable to list PO lines.") from exc


def get_procurement_pipeline_summary(
    destination_warehouse_id: str | None = None,
    supplier_id: str | None = None,
    status_in: list[str] | None = None,
    horizon_days: int | None = None,
    group_by: str = ProcurementGroupBy.warehouse_supplier.value,
    include_names: bool = False,
) -> ToolResult[ProcurementPipelineSummaryResponse]:
    """
    USE THIS TOOL to summarize inbound procurement pipeline by warehouse/supplier grouping.
    """
    try:
        request = ProcurementPipelineSummaryRequest(
            destination_warehouse_id=_parse_optional_uuid(
                destination_warehouse_id, "destination_warehouse_id"
            ),
            supplier_id=_parse_optional_uuid(supplier_id, "supplier_id"),
            status_in=_parse_status_list(status_in),
            horizon_days=horizon_days,
            group_by=_parse_group_by(group_by),
            include_names=include_names,
        )

        with get_session() as session:
            rows = fetch_procurement_pipeline_summary_rows(session, request)

        response = ProcurementPipelineSummaryResponse(
            rows=[_pipeline_row_from_row(row) for row in rows]
        )
        return ToolResult(
            data=response,
            message=(
                "No procurement pipeline rows matched filters."
                if not response.rows
                else f"Retrieved {len(response.rows)} procurement pipeline rows."
            ),
            meta={
                "count": len(response.rows),
                "filters": {
                    "destination_warehouse_id": (
                        str(request.destination_warehouse_id)
                        if request.destination_warehouse_id
                        else None
                    ),
                    "supplier_id": str(request.supplier_id) if request.supplier_id else None,
                    "status_in": _serialize_statuses(request.status_in),
                    "horizon_days": request.horizon_days,
                    "group_by": request.group_by.value,
                    "include_names": request.include_names,
                },
            },
        )
    except Exception as exc:
        raise RuntimeError("Unable to get procurement pipeline summary.") from exc
