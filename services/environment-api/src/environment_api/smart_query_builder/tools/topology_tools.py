from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from common.schemas.common import Pagination, ToolResult, ToolResultMeta, build_tool_meta
from common.schemas.topology import (
    GetLocationRequest,
    GetLocationResponse,
    GetWarehouseCapacityUtilizationRequest,
    GetWarehouseCapacityUtilizationResponse,
    GetWarehouseLocationsTreeRequest,
    GetWarehouseLocationsTreeResponse,
    GetWarehouseRequest,
    GetWarehouseResponse,
    ListLocationsRequest,
    ListLocationsResponse,
    ListWarehousesRequest,
    ListWarehousesResponse,
    LocationCapacityUtilizationRow,
    LocationOut,
    LocationTreeNode,
    TopologyLocationType,
    WarehouseOut,
)

from ..db.session import get_session
from ..repo.topology import (
    fetch_capacity_utilization_rows,
    fetch_location_row,
    fetch_location_rows,
    fetch_warehouse_location_rows,
    fetch_warehouse_row,
    fetch_warehouse_rows,
)


def _parse_uuid(value: str, field_name: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as exc:
        raise ValueError(f"Invalid UUID for {field_name}: {value!r}") from exc


def _parse_optional_uuid(value: str | None, field_name: str) -> UUID | None:
    if value is None:
        return None
    return _parse_uuid(value, field_name)


def _parse_optional_location_type(value: str | None) -> TopologyLocationType | None:
    if value is None:
        return None
    return TopologyLocationType(value)


def _to_int(value: Any, field_name: str) -> int:
    if value is None:
        raise ValueError(f"Unexpected null value for {field_name}.")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid integer value for {field_name}: {value!r}") from exc


def _to_optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _to_location_type(value: Any, field_name: str = "type") -> TopologyLocationType:
    if value is None:
        raise ValueError(f"Unexpected null value for {field_name}.")

    if hasattr(value, "value"):
        raw = str(value.value)
    elif hasattr(value, "name"):
        raw = str(value.name).lower()
    else:
        raw = str(value)
        if "." in raw:
            raw = raw.rsplit(".", 1)[-1]
        raw = raw.lower()

    try:
        return TopologyLocationType(raw)
    except ValueError as exc:
        raise ValueError(f"Invalid location type for {field_name}: {value!r}") from exc


def _warehouse_from_row(row: Any) -> WarehouseOut:
    return WarehouseOut(
        id=row["id"],
        name=str(row["name"]),
        region=str(row["region"]),
        tz=str(row["tz"]),
    )


def _location_from_row(row: Any) -> LocationOut:
    return LocationOut(
        id=row["id"],
        warehouse_id=row["warehouse_id"],
        parent_location_id=row["parent_location_id"],
        code=str(row["code"]),
        type=_to_location_type(row["type"]),
        capacity_units=_to_int(row["capacity_units"], "capacity_units"),
    )


def _tree_node_from_location(location: LocationOut) -> LocationTreeNode:
    return LocationTreeNode(
        id=location.id,
        warehouse_id=location.warehouse_id,
        parent_location_id=location.parent_location_id,
        code=location.code,
        type=location.type,
        capacity_units=location.capacity_units,
        children=[],
    )


def _resolve_window(
    request: GetWarehouseCapacityUtilizationRequest,
) -> tuple[datetime, datetime]:
    if request.snapshot_at is not None:
        window_end = request.snapshot_at
        window_start = request.snapshot_at - timedelta(hours=request.lookback_hours)
        return window_start, window_end

    if request.observed_from is None or request.observed_to is None:
        raise RuntimeError("Unable to resolve observation window from request.")

    return request.observed_from, request.observed_to


def _sort_tree(nodes: list[LocationTreeNode]) -> None:
    nodes.sort(key=lambda node: (node.code, str(node.id)))
    for node in nodes:
        _sort_tree(node.children)


def _build_location_tree(flat_locations: list[LocationOut]) -> list[LocationTreeNode]:
    nodes_by_id = {location.id: _tree_node_from_location(location) for location in flat_locations}

    roots: list[LocationTreeNode] = []
    for location in flat_locations:
        node = nodes_by_id[location.id]
        parent_id = location.parent_location_id
        if parent_id is not None and parent_id in nodes_by_id:
            nodes_by_id[parent_id].children.append(node)
        else:
            roots.append(node)

    _sort_tree(roots)
    return roots


def _capacity_row_from_row(row: Any) -> LocationCapacityUtilizationRow:
    return LocationCapacityUtilizationRow(
        location_id=row["location_id"],
        capacity_units=_to_int(row["capacity_units"], "capacity_units"),
        observed_qty_sum=_to_optional_float(row["observed_qty_sum"]),
        utilization_estimate=_to_optional_float(row["utilization_estimate"]),
        confidence_avg=_to_optional_float(row["confidence_avg"]),
        obs_count=_to_int(row["obs_count"], "obs_count"),
    )


def _map_capacity_rows(rows: Sequence[Any]) -> list[LocationCapacityUtilizationRow]:
    return [_capacity_row_from_row(row) for row in rows]


def _calculate_capacity_totals(
    data_rows: list[LocationCapacityUtilizationRow],
) -> tuple[float | None, int, float | None]:
    observed_values = [
        row.observed_qty_sum for row in data_rows if row.observed_qty_sum is not None
    ]
    total_observed_qty_sum = sum(observed_values) if observed_values else None
    total_capacity_units = sum(row.capacity_units for row in data_rows)
    utilization_estimate = (
        total_observed_qty_sum / total_capacity_units
        if total_observed_qty_sum is not None and total_capacity_units > 0
        else None
    )
    return total_observed_qty_sum, total_capacity_units, utilization_estimate


def _capacity_message(location_count: int) -> str:
    if location_count == 0:
        return "No locations matched capacity utilization filters."
    return f"Retrieved capacity utilization snapshot for {location_count} locations."


def _capacity_meta(
    warehouse_id: str,
    request: GetWarehouseCapacityUtilizationRequest,
    row_count: int,
    window_start: datetime,
    window_end: datetime,
) -> ToolResultMeta:
    return build_tool_meta(
        count=row_count,
        filters={
            "warehouse_id": warehouse_id,
            "type": request.type.value if request.type else None,
            "snapshot_at": request.snapshot_at.isoformat() if request.snapshot_at else None,
            "observed_from": request.observed_from.isoformat() if request.observed_from else None,
            "observed_to": request.observed_to.isoformat() if request.observed_to else None,
            "lookback_hours": request.lookback_hours,
        },
        observation_window={
            "start": window_start.isoformat(),
            "end": window_end.isoformat(),
        },
    )


def list_warehouses(
    region: str | None = None,
    name_like: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> ToolResult[ListWarehousesResponse]:
    """
    USE THIS TOOL to list warehouses with optional region/name filters.
    """
    try:
        request = ListWarehousesRequest(
            region=region,
            name_like=name_like,
            limit=limit,
            offset=offset,
        )

        with get_session() as session:
            rows = fetch_warehouse_rows(session, request)

        response = ListWarehousesResponse(warehouses=[_warehouse_from_row(row) for row in rows])
        return ToolResult(
            data=response,
            message=(
                "No warehouses matched filters."
                if not response.warehouses
                else f"Retrieved {len(response.warehouses)} warehouses."
            ),
            meta=build_tool_meta(
                count=len(response.warehouses),
                filters={
                    "region": request.region,
                    "name_like": request.name_like,
                },
                pagination=Pagination(limit=request.limit, offset=request.offset),
            ),
        )
    except Exception as exc:
        raise RuntimeError("Unable to list warehouses.") from exc


def get_warehouse(
    warehouse_id: str,
) -> ToolResult[GetWarehouseResponse]:
    """
    USE THIS TOOL to retrieve warehouse details by warehouse UUID.
    """
    try:
        request = GetWarehouseRequest(warehouse_id=_parse_uuid(warehouse_id, "warehouse_id"))

        with get_session() as session:
            row = fetch_warehouse_row(session, request)

        if row is None:
            raise ValueError(f"Warehouse not found: {warehouse_id}")

        response = GetWarehouseResponse(warehouse=_warehouse_from_row(row))
        return ToolResult(
            data=response,
            message="Retrieved warehouse details.",
            meta=build_tool_meta(count=1, warehouse_id=warehouse_id),
        )
    except Exception as exc:
        raise RuntimeError("Unable to get warehouse.") from exc


def list_locations(
    warehouse_id: str | None = None,
    type: str | None = None,
    parent_location_id: str | None = None,
    code_like: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> ToolResult[ListLocationsResponse]:
    """
    USE THIS TOOL to list warehouse locations as a flat structure.
    """
    try:
        request = ListLocationsRequest(
            warehouse_id=_parse_optional_uuid(warehouse_id, "warehouse_id"),
            type=_parse_optional_location_type(type),
            parent_location_id=_parse_optional_uuid(parent_location_id, "parent_location_id"),
            code_like=code_like,
            limit=limit,
            offset=offset,
        )

        with get_session() as session:
            rows = fetch_location_rows(session, request)

        response = ListLocationsResponse(locations=[_location_from_row(row) for row in rows])
        return ToolResult(
            data=response,
            message=(
                "No locations matched filters."
                if not response.locations
                else f"Retrieved {len(response.locations)} locations."
            ),
            meta=build_tool_meta(
                count=len(response.locations),
                filters={
                    "warehouse_id": str(request.warehouse_id) if request.warehouse_id else None,
                    "type": request.type.value if request.type else None,
                    "parent_location_id": (
                        str(request.parent_location_id) if request.parent_location_id else None
                    ),
                    "code_like": request.code_like,
                },
                pagination=Pagination(limit=request.limit, offset=request.offset),
            ),
        )
    except Exception as exc:
        raise RuntimeError("Unable to list locations.") from exc


def get_location(
    location_id: str,
) -> ToolResult[GetLocationResponse]:
    """
    USE THIS TOOL to retrieve location details by location UUID.
    """
    try:
        request = GetLocationRequest(location_id=_parse_uuid(location_id, "location_id"))

        with get_session() as session:
            row = fetch_location_row(session, request)

        if row is None:
            raise ValueError(f"Location not found: {location_id}")

        response = GetLocationResponse(location=_location_from_row(row))
        return ToolResult(
            data=response,
            message="Retrieved location details.",
            meta=build_tool_meta(count=1, location_id=location_id),
        )
    except Exception as exc:
        raise RuntimeError("Unable to get location.") from exc


def get_locations_tree(
    warehouse_id: str,
) -> ToolResult[GetWarehouseLocationsTreeResponse]:
    """
    USE THIS TOOL to reconstruct hierarchical location topology for a warehouse.
    """
    try:
        request = GetWarehouseLocationsTreeRequest(
            warehouse_id=_parse_uuid(warehouse_id, "warehouse_id")
        )

        with get_session() as session:
            warehouse_row = fetch_warehouse_row(
                session, GetWarehouseRequest(warehouse_id=request.warehouse_id)
            )
            if warehouse_row is None:
                raise ValueError(f"Warehouse not found: {warehouse_id}")
            rows = fetch_warehouse_location_rows(session, request)

        flat_locations = [_location_from_row(row) for row in rows]
        roots = _build_location_tree(flat_locations)

        response = GetWarehouseLocationsTreeResponse(
            warehouse_id=request.warehouse_id,
            warehouse_name=str(warehouse_row["name"]),
            roots=roots,
            node_count=len(flat_locations),
            root_count=len(roots),
        )

        return ToolResult(
            data=response,
            message=(
                "No locations found for warehouse."
                if not response.roots
                else f"Retrieved location tree with {response.node_count} nodes."
            ),
            meta=build_tool_meta(
                count=response.node_count,
                warehouse_id=warehouse_id,
                node_count=response.node_count,
                root_count=response.root_count,
            ),
        )
    except Exception as exc:
        raise RuntimeError("Unable to get locations tree.") from exc


def get_capacity_utilization_snapshot(
    warehouse_id: str,
    snapshot_at: datetime | None = None,
    observed_from: datetime | None = None,
    observed_to: datetime | None = None,
    lookback_hours: int = 24,
    type: str | None = None,
) -> ToolResult[GetWarehouseCapacityUtilizationResponse]:
    """
    USE THIS TOOL for capacity planning under partial observability from observations.
    """
    try:
        request = GetWarehouseCapacityUtilizationRequest(
            warehouse_id=_parse_uuid(warehouse_id, "warehouse_id"),
            snapshot_at=snapshot_at,
            observed_from=observed_from,
            observed_to=observed_to,
            lookback_hours=lookback_hours,
            type=_parse_optional_location_type(type),
        )

        with get_session() as session:
            warehouse_row = fetch_warehouse_row(
                session, GetWarehouseRequest(warehouse_id=request.warehouse_id)
            )
            if warehouse_row is None:
                raise ValueError(f"Warehouse not found: {warehouse_id}")

            rows = fetch_capacity_utilization_rows(session, request)

        data_rows = _map_capacity_rows(rows)
        total_observed_qty_sum, total_capacity_units, utilization_estimate = (
            _calculate_capacity_totals(data_rows)
        )
        window_start, window_end = _resolve_window(request)

        response = GetWarehouseCapacityUtilizationResponse(
            warehouse_id=request.warehouse_id,
            warehouse_name=str(warehouse_row["name"]),
            location_count=len(data_rows),
            total_capacity_units=total_capacity_units,
            total_observed_qty_sum=total_observed_qty_sum,
            utilization_estimate=utilization_estimate,
            rows=data_rows,
        )

        return ToolResult(
            data=response,
            message=_capacity_message(len(response.rows)),
            meta=_capacity_meta(
                warehouse_id=warehouse_id,
                request=request,
                row_count=len(response.rows),
                window_start=window_start,
                window_end=window_end,
            ),
        )
    except Exception as exc:
        raise RuntimeError("Unable to get capacity utilization snapshot.") from exc
