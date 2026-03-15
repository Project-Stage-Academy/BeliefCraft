from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from common.schemas.procurement import (
    GetPurchaseOrderRequest,
    GetSupplierRequest,
    ListPoLinesRequest,
    ListPurchaseOrdersRequest,
    ListSuppliersRequest,
    ProcurementGroupBy,
    ProcurementPipelineSummaryRequest,
)
from database.inventory import Product
from database.logistics import Supplier, Warehouse
from database.orders import POLine, PurchaseOrder
from sqlalchemy import func, literal, select
from sqlalchemy.engine import RowMapping
from sqlalchemy.orm import Session
from sqlalchemy.sql.selectable import FromClause

_PROCUREMENT_TABLES: dict[str, FromClause] = {
    "suppliers": Supplier.__table__,
    "purchase_orders": PurchaseOrder.__table__,
    "po_lines": POLine.__table__,
    "products": Product.__table__,
    "warehouses": Warehouse.__table__,
}


def _load_tables(session: Session) -> dict[str, FromClause]:
    if session.get_bind() is None:
        raise RuntimeError("Database session is not bound.")

    return _PROCUREMENT_TABLES.copy()


def _build_optional_name_columns(
    include_names: bool, suppliers: Any, warehouses: Any
) -> tuple[Any, Any]:
    supplier_name_col = (
        suppliers.c.name.label("supplier_name")
        if include_names
        else literal(None).label("supplier_name")
    )
    warehouse_name_col = (
        warehouses.c.name.label("warehouse_name")
        if include_names
        else literal(None).label("warehouse_name")
    )
    return supplier_name_col, warehouse_name_col


def _build_purchase_orders_from_clause(
    include_names: bool,
    purchase_orders: Any,
    suppliers: Any,
    warehouses: Any,
) -> Any:
    if not include_names:
        return purchase_orders
    return purchase_orders.join(suppliers, suppliers.c.id == purchase_orders.c.supplier_id).join(
        warehouses, warehouses.c.id == purchase_orders.c.destination_warehouse_id
    )


def _build_procurement_pipeline_from_clause(
    include_names: bool,
    purchase_orders: Any,
    po_lines: Any,
    suppliers: Any,
    warehouses: Any,
) -> Any:
    from_clause = purchase_orders.join(
        po_lines, po_lines.c.purchase_order_id == purchase_orders.c.id
    )
    if not include_names:
        return from_clause
    return from_clause.join(suppliers, suppliers.c.id == purchase_orders.c.supplier_id).join(
        warehouses, warehouses.c.id == purchase_orders.c.destination_warehouse_id
    )


@dataclass(frozen=True)
class _ProcurementPipelineGroupingSpec:
    destination_id_col: Any
    supplier_id_col: Any
    supplier_name_col: Any
    warehouse_name_col: Any
    group_cols: tuple[Any, ...]


def _procurement_pipeline_grouping_by_warehouse(
    include_names: bool,
    purchase_orders: Any,
    _suppliers: Any,
    warehouses: Any,
) -> _ProcurementPipelineGroupingSpec:
    destination_id_col = purchase_orders.c.destination_warehouse_id
    supplier_id_col = literal(None)
    supplier_name_col = literal(None)
    warehouse_name_col = warehouses.c.name if include_names else literal(None)
    group_cols: tuple[Any, ...] = (destination_id_col, supplier_id_col)
    if include_names:
        group_cols = (*group_cols, warehouses.c.name)
    return _ProcurementPipelineGroupingSpec(
        destination_id_col=destination_id_col,
        supplier_id_col=supplier_id_col,
        supplier_name_col=supplier_name_col,
        warehouse_name_col=warehouse_name_col,
        group_cols=group_cols,
    )


def _procurement_pipeline_grouping_by_supplier(
    include_names: bool,
    purchase_orders: Any,
    suppliers: Any,
    _warehouses: Any,
) -> _ProcurementPipelineGroupingSpec:
    destination_id_col = literal(None)
    supplier_id_col = purchase_orders.c.supplier_id
    supplier_name_col = suppliers.c.name if include_names else literal(None)
    warehouse_name_col = literal(None)
    group_cols: tuple[Any, ...] = (destination_id_col, supplier_id_col)
    if include_names:
        group_cols = (*group_cols, suppliers.c.name)
    return _ProcurementPipelineGroupingSpec(
        destination_id_col=destination_id_col,
        supplier_id_col=supplier_id_col,
        supplier_name_col=supplier_name_col,
        warehouse_name_col=warehouse_name_col,
        group_cols=group_cols,
    )


def _procurement_pipeline_grouping_by_warehouse_supplier(
    include_names: bool,
    purchase_orders: Any,
    suppliers: Any,
    warehouses: Any,
) -> _ProcurementPipelineGroupingSpec:
    destination_id_col = purchase_orders.c.destination_warehouse_id
    supplier_id_col = purchase_orders.c.supplier_id
    supplier_name_col = suppliers.c.name if include_names else literal(None)
    warehouse_name_col = warehouses.c.name if include_names else literal(None)
    group_cols: tuple[Any, ...] = (destination_id_col, supplier_id_col)
    if include_names:
        group_cols = (*group_cols, suppliers.c.name, warehouses.c.name)
    return _ProcurementPipelineGroupingSpec(
        destination_id_col=destination_id_col,
        supplier_id_col=supplier_id_col,
        supplier_name_col=supplier_name_col,
        warehouse_name_col=warehouse_name_col,
        group_cols=group_cols,
    )


def _build_procurement_pipeline_grouping_spec(
    group_by: ProcurementGroupBy,
    include_names: bool,
    purchase_orders: Any,
    suppliers: Any,
    warehouses: Any,
) -> _ProcurementPipelineGroupingSpec:
    if group_by == ProcurementGroupBy.warehouse:
        return _procurement_pipeline_grouping_by_warehouse(
            include_names, purchase_orders, suppliers, warehouses
        )
    if group_by == ProcurementGroupBy.supplier:
        return _procurement_pipeline_grouping_by_supplier(
            include_names, purchase_orders, suppliers, warehouses
        )
    return _procurement_pipeline_grouping_by_warehouse_supplier(
        include_names, purchase_orders, suppliers, warehouses
    )


def _status_values(statuses: Sequence[object]) -> list[str]:
    values: list[str] = []
    for status in statuses:
        if hasattr(status, "name"):
            values.append(str(status.name))  # SUBMITTED
        else:
            values.append(str(getattr(status, "value", status)).upper())
    return values


def fetch_supplier_rows(
    session: Session,
    request: ListSuppliersRequest,
) -> Sequence[RowMapping]:
    tables = _load_tables(session)
    suppliers = tables["suppliers"]

    stmt = (
        select(
            suppliers.c.id.label("id"),
            suppliers.c.name.label("name"),
            suppliers.c.reliability_score.label("reliability_score"),
            suppliers.c.region.label("region"),
        )
        .select_from(suppliers)
        .order_by(suppliers.c.name.asc(), suppliers.c.id.asc())
        .limit(request.limit)
        .offset(request.offset)
    )

    if request.region:
        stmt = stmt.where(suppliers.c.region == request.region)
    if request.reliability_min is not None:
        stmt = stmt.where(suppliers.c.reliability_score >= request.reliability_min)
    if request.reliability_max is not None:
        stmt = stmt.where(suppliers.c.reliability_score <= request.reliability_max)
    if request.name_like:
        stmt = stmt.where(suppliers.c.name.ilike(f"%{request.name_like}%"))

    return session.execute(stmt).mappings().all()


def fetch_supplier_row(
    session: Session,
    request: GetSupplierRequest,
) -> RowMapping | None:
    tables = _load_tables(session)
    suppliers = tables["suppliers"]

    stmt = (
        select(
            suppliers.c.id.label("id"),
            suppliers.c.name.label("name"),
            suppliers.c.reliability_score.label("reliability_score"),
            suppliers.c.region.label("region"),
        )
        .select_from(suppliers)
        .where(suppliers.c.id == request.supplier_id)
        .limit(1)
    )
    return session.execute(stmt).mappings().one_or_none()


def fetch_purchase_order_rows(
    session: Session,
    request: ListPurchaseOrdersRequest,
) -> Sequence[RowMapping]:
    tables = _load_tables(session)
    purchase_orders = tables["purchase_orders"]
    suppliers = tables["suppliers"]
    warehouses = tables["warehouses"]

    supplier_name_col, warehouse_name_col = _build_optional_name_columns(
        request.include_names, suppliers, warehouses
    )

    from_clause = _build_purchase_orders_from_clause(
        request.include_names, purchase_orders, suppliers, warehouses
    )

    stmt = (
        select(
            purchase_orders.c.id.label("id"),
            purchase_orders.c.supplier_id.label("supplier_id"),
            purchase_orders.c.destination_warehouse_id.label("destination_warehouse_id"),
            purchase_orders.c.status.label("status"),
            purchase_orders.c.expected_at.label("expected_at"),
            purchase_orders.c.leadtime_model_id.label("leadtime_model_id"),
            purchase_orders.c.created_at.label("created_at"),
            supplier_name_col,
            warehouse_name_col,
        )
        .select_from(from_clause)
        .order_by(purchase_orders.c.created_at.desc(), purchase_orders.c.id.asc())
        .limit(request.limit)
        .offset(request.offset)
    )

    if request.supplier_id:
        stmt = stmt.where(purchase_orders.c.supplier_id == request.supplier_id)
    if request.destination_warehouse_id:
        stmt = stmt.where(
            purchase_orders.c.destination_warehouse_id == request.destination_warehouse_id
        )
    if request.status_in:
        stmt = stmt.where(purchase_orders.c.status.in_(_status_values(request.status_in)))
    if request.created_after:
        stmt = stmt.where(purchase_orders.c.created_at >= request.created_after)
    if request.created_before:
        stmt = stmt.where(purchase_orders.c.created_at <= request.created_before)
    if request.expected_after:
        stmt = stmt.where(purchase_orders.c.expected_at >= request.expected_after)
    if request.expected_before:
        stmt = stmt.where(purchase_orders.c.expected_at <= request.expected_before)

    return session.execute(stmt).mappings().all()


def fetch_purchase_order_row(
    session: Session,
    request: GetPurchaseOrderRequest,
) -> RowMapping | None:
    tables = _load_tables(session)
    purchase_orders = tables["purchase_orders"]
    suppliers = tables["suppliers"]
    warehouses = tables["warehouses"]

    supplier_name_col, warehouse_name_col = _build_optional_name_columns(
        request.include_names, suppliers, warehouses
    )

    from_clause = _build_purchase_orders_from_clause(
        request.include_names, purchase_orders, suppliers, warehouses
    )

    stmt = (
        select(
            purchase_orders.c.id.label("id"),
            purchase_orders.c.supplier_id.label("supplier_id"),
            purchase_orders.c.destination_warehouse_id.label("destination_warehouse_id"),
            purchase_orders.c.status.label("status"),
            purchase_orders.c.expected_at.label("expected_at"),
            purchase_orders.c.leadtime_model_id.label("leadtime_model_id"),
            purchase_orders.c.created_at.label("created_at"),
            supplier_name_col,
            warehouse_name_col,
        )
        .select_from(from_clause)
        .where(purchase_orders.c.id == request.purchase_order_id)
        .limit(1)
    )
    return session.execute(stmt).mappings().one_or_none()


def fetch_po_line_rows(
    session: Session,
    request: ListPoLinesRequest,
) -> Sequence[RowMapping]:
    tables = _load_tables(session)
    po_lines = tables["po_lines"]
    products = tables["products"]

    remaining_qty_expr = func.greatest(
        func.coalesce(po_lines.c.qty_ordered, 0) - func.coalesce(po_lines.c.qty_received, 0),
        0,
    ).label("remaining_qty")
    sku_col = (
        products.c.sku.label("sku")
        if request.include_product_fields
        else literal(None).label("sku")
    )
    product_name_col = (
        products.c.name.label("product_name")
        if request.include_product_fields
        else literal(None).label("product_name")
    )
    category_col = (
        products.c.category.label("category")
        if request.include_product_fields
        else literal(None).label("category")
    )

    from_clause: Any = po_lines
    if request.include_product_fields:
        from_clause = from_clause.join(products, products.c.id == po_lines.c.product_id)

    stmt = (
        select(
            po_lines.c.id.label("id"),
            po_lines.c.purchase_order_id.label("purchase_order_id"),
            po_lines.c.product_id.label("product_id"),
            po_lines.c.qty_ordered.label("qty_ordered"),
            po_lines.c.qty_received.label("qty_received"),
            remaining_qty_expr,
            sku_col,
            product_name_col,
            category_col,
        )
        .select_from(from_clause)
        .order_by(po_lines.c.purchase_order_id.asc(), po_lines.c.id.asc())
    )

    if request.purchase_order_id:
        stmt = stmt.where(po_lines.c.purchase_order_id == request.purchase_order_id)
    if request.purchase_order_ids:
        stmt = stmt.where(po_lines.c.purchase_order_id.in_(request.purchase_order_ids))
    if request.product_id:
        stmt = stmt.where(po_lines.c.product_id == request.product_id)

    return session.execute(stmt).mappings().all()


def fetch_procurement_pipeline_summary_rows(
    session: Session,
    request: ProcurementPipelineSummaryRequest,
) -> Sequence[RowMapping]:
    tables = _load_tables(session)
    purchase_orders = tables["purchase_orders"]
    po_lines = tables["po_lines"]
    suppliers = tables["suppliers"]
    warehouses = tables["warehouses"]

    from_clause = _build_procurement_pipeline_from_clause(
        request.include_names, purchase_orders, po_lines, suppliers, warehouses
    )
    grouping_spec = _build_procurement_pipeline_grouping_spec(
        request.group_by, request.include_names, purchase_orders, suppliers, warehouses
    )

    remaining_line_qty_expr = func.greatest(
        func.coalesce(po_lines.c.qty_ordered, 0) - func.coalesce(po_lines.c.qty_received, 0),
        0,
    )

    stmt = select(
        grouping_spec.destination_id_col.label("destination_warehouse_id"),
        grouping_spec.supplier_id_col.label("supplier_id"),
        func.count(func.distinct(purchase_orders.c.id)).label("po_count"),
        func.coalesce(func.sum(po_lines.c.qty_ordered), 0.0).label("total_qty_ordered"),
        func.coalesce(func.sum(po_lines.c.qty_received), 0.0).label("total_qty_received"),
        func.coalesce(func.sum(remaining_line_qty_expr), 0.0).label("total_qty_remaining"),
        func.min(purchase_orders.c.expected_at).label("next_expected_at"),
        func.max(purchase_orders.c.created_at).label("last_created_at"),
        grouping_spec.supplier_name_col.label("supplier_name"),
        grouping_spec.warehouse_name_col.label("warehouse_name"),
    ).select_from(from_clause)

    if request.destination_warehouse_id:
        stmt = stmt.where(
            purchase_orders.c.destination_warehouse_id == request.destination_warehouse_id
        )
    if request.supplier_id:
        stmt = stmt.where(purchase_orders.c.supplier_id == request.supplier_id)
    if request.status_in:
        stmt = stmt.where(purchase_orders.c.status.in_(_status_values(request.status_in)))
    if request.horizon_days is not None:
        horizon_cutoff = datetime.now(UTC) + timedelta(days=request.horizon_days)
        stmt = stmt.where(
            purchase_orders.c.expected_at.is_not(None),
            purchase_orders.c.expected_at <= horizon_cutoff,
        )

    stmt = stmt.group_by(*grouping_spec.group_cols).order_by(
        func.min(purchase_orders.c.expected_at).asc().nulls_last(),
        func.coalesce(func.sum(remaining_line_qty_expr), 0.0).desc(),
    )

    return session.execute(stmt).mappings().all()
