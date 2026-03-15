"""
Environment tools for querying warehouse state via smart-query API.

This module provides tools that allow the ReAct agent to:
- Query procurement data (suppliers, purchase orders, PO lines, pipeline)
- Retrieve inventory history and audit trails
- Get warehouse topology and capacity information
- Monitor sensor device health and anomalies
- Access observed inventory snapshots with quality filtering

All tools use EnvironmentAPIClient to communicate with the Environment API
service with automatic retry logic and error handling.

Organized by module:
- PROCUREMENT MODULE: 6 tools
- INVENTORY AUDIT MODULE: 4 tools
- TOPOLOGY MODULE: 6 tools
- DEVICE MONITORING MODULE: 4 tools
- OBSERVED INVENTORY MODULE: 1 tool
Total: 21 tools
"""

from typing import Any, cast

from app.clients.environment_client import (
    EnvironmentAPIClient,
    EnvironmentClientProtocol,
)
from app.core.constants import (
    CACHE_TTL_ANALYTICS,
    CACHE_TTL_HISTORY,
    CACHE_TTL_SHIPMENTS,
)
from app.tools.base import APIClientTool, ToolMetadata

# ========================================
# PROCUREMENT MODULE (6 tools)
# ========================================


class ListSuppliersTool(APIClientTool):
    """Get list of suppliers with reliability and region metadata."""

    def __init__(self, client: EnvironmentClientProtocol | None = None) -> None:
        self._client = client
        super().__init__()

    def get_client(self) -> EnvironmentClientProtocol:
        return (
            self._client
            if self._client
            else cast(EnvironmentClientProtocol, EnvironmentAPIClient())
        )

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="list_suppliers",
            description=(
                "Get list of suppliers with reliability scores and region. "
                "Use to filter suppliers before procurement analysis."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "region": {
                        "type": "string",
                        "description": "Optional: Filter by region (e.g., 'US', 'EU')",
                    },
                    "reliability_min": {
                        "type": "number",
                        "description": "Optional: Minimum reliability score (0-1)",
                    },
                    "name_like": {
                        "type": "string",
                        "description": "Optional: Filter by supplier name pattern",
                    },
                },
                "required": [],
            },
            category="environment",
            cache_ttl=CACHE_TTL_ANALYTICS,
        )

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        async with self.get_client() as client:
            return await client.list_suppliers(
                region=kwargs.get("region"),
                reliability_min=kwargs.get("reliability_min"),
                name_like=kwargs.get("name_like"),
            )


class GetSupplierTool(APIClientTool):
    """Get detailed information for a single supplier."""

    def __init__(self, client: EnvironmentClientProtocol | None = None) -> None:
        self._client = client
        super().__init__()

    def get_client(self) -> EnvironmentClientProtocol:
        return (
            self._client
            if self._client
            else cast(EnvironmentClientProtocol, EnvironmentAPIClient())
        )

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="get_supplier",
            description=(
                "Get detailed information for a specific supplier. "
                "Use for analyzing supplier reliability and risk."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "supplier_id": {"type": "string", "description": "Supplier ID (UUID)"},
                },
                "required": ["supplier_id"],
            },
            category="environment",
            cache_ttl=CACHE_TTL_ANALYTICS,
        )

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        self._validate_required_params(["supplier_id"], kwargs)
        async with self.get_client() as client:
            return await client.get_supplier(supplier_id=kwargs["supplier_id"])


class ListPurchaseOrdersTool(APIClientTool):
    """Get purchase orders with filtering capabilities."""

    def __init__(self, client: EnvironmentClientProtocol | None = None) -> None:
        self._client = client
        super().__init__()

    def get_client(self) -> EnvironmentClientProtocol:
        return (
            self._client
            if self._client
            else cast(EnvironmentClientProtocol, EnvironmentAPIClient())
        )

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="list_purchase_orders",
            description=(
                "Get purchase orders with filters. " "Core entry point for inbound supply tracking."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "supplier_id": {
                        "type": "string",
                        "description": "Optional: Filter by supplier ID",
                    },
                    "destination_warehouse_id": {
                        "type": "string",
                        "description": "Optional: Filter by warehouse",
                    },
                    "status_in": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": ["draft", "submitted", "partial", "received", "closed"],
                        },
                        "description": (
                            "Optional: Filter by status list. "
                            "Valid statuses are: 'draft', 'submitted', 'partial', "
                            "'received', 'closed'. (e.g., ['submitted', 'partial'])"
                        ),
                    },
                    "created_after": {
                        "type": "string",
                        "description": "Optional: ISO timestamp (created after)",
                    },
                    "expected_before": {
                        "type": "string",
                        "description": "Optional: ISO timestamp (expected before)",
                    },
                },
                "required": [],
            },
            category="environment",
            cache_ttl=CACHE_TTL_SHIPMENTS,
        )

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        async with self.get_client() as client:
            return await client.list_purchase_orders(
                supplier_id=kwargs.get("supplier_id"),
                destination_warehouse_id=kwargs.get("destination_warehouse_id"),
                status_in=kwargs.get("status_in"),
                created_after=kwargs.get("created_after"),
                expected_before=kwargs.get("expected_before"),
            )


class GetPurchaseOrderTool(APIClientTool):
    """Get a single purchase order."""

    def __init__(self, client: EnvironmentClientProtocol | None = None) -> None:
        self._client = client
        super().__init__()

    def get_client(self) -> EnvironmentClientProtocol:
        return (
            self._client
            if self._client
            else cast(EnvironmentClientProtocol, EnvironmentAPIClient())
        )

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="get_purchase_order",
            description="Get detailed information for a specific purchase order.",
            parameters={
                "type": "object",
                "properties": {
                    "purchase_order_id": {
                        "type": "string",
                        "description": "Purchase order ID (UUID)",
                    },
                },
                "required": ["purchase_order_id"],
            },
            category="environment",
            cache_ttl=CACHE_TTL_SHIPMENTS,
        )

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        self._validate_required_params(["purchase_order_id"], kwargs)
        async with self.get_client() as client:
            return await client.get_purchase_order(purchase_order_id=kwargs["purchase_order_id"])


class ListPOLinesTool(APIClientTool):
    """Get line-level details for purchase orders (product-level inbound analysis)."""

    def __init__(self, client: EnvironmentClientProtocol | None = None) -> None:
        self._client = client
        super().__init__()

    def get_client(self) -> EnvironmentClientProtocol:
        return (
            self._client
            if self._client
            else cast(EnvironmentClientProtocol, EnvironmentAPIClient())
        )

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="list_po_lines",
            description=(
                "Get purchase order line items (product-level details). "
                "Use for product-level inbound analysis."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "purchase_order_id": {
                        "type": "string",
                        "description": "Optional: Single PO ID",
                    },
                    "purchase_order_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional: Multiple PO IDs",
                    },
                },
                "required": [],
            },
            category="environment",
            cache_ttl=CACHE_TTL_SHIPMENTS,
        )

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        async with self.get_client() as client:
            return await client.list_po_lines(
                purchase_order_id=kwargs.get("purchase_order_id"),
                purchase_order_ids=kwargs.get("purchase_order_ids"),
            )


class GetProcurementPipelineSummaryTool(APIClientTool):
    """Get aggregated inbound supply pipeline metrics."""

    def __init__(self, client: EnvironmentClientProtocol | None = None) -> None:
        self._client = client
        super().__init__()

    def get_client(self) -> EnvironmentClientProtocol:
        return (
            self._client
            if self._client
            else cast(EnvironmentClientProtocol, EnvironmentAPIClient())
        )

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="get_procurement_pipeline_summary",
            description=(
                "Get aggregated inbound supply pipeline metrics by warehouse "
                "or supplier. Primary tool for analyzing inbound supply pipelines."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "destination_warehouse_id": {
                        "type": "string",
                        "description": "Optional: Filter by warehouse",
                    },
                    "supplier_id": {
                        "type": "string",
                        "description": "Optional: Filter by supplier",
                    },
                    "status_in": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional: Filter by status list",
                    },
                    "horizon_days": {
                        "type": "integer",
                        "description": "Optional: Forecast horizon in days",
                    },
                },
                "required": [],
            },
            category="environment",
            cache_ttl=CACHE_TTL_ANALYTICS,
        )

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        async with self.get_client() as client:
            return await client.get_procurement_pipeline_summary(
                destination_warehouse_id=kwargs.get("destination_warehouse_id"),
                supplier_id=kwargs.get("supplier_id"),
                status_in=kwargs.get("status_in"),
                horizon_days=kwargs.get("horizon_days"),
            )


# ========================================
# INVENTORY AUDIT MODULE (4 tools)
# ========================================


class ListInventoryMovesTool(APIClientTool):
    """Get inventory movement history (core movement ledger for operational traceability)."""

    def __init__(self, client: EnvironmentClientProtocol | None = None) -> None:
        self._client = client
        super().__init__()

    def get_client(self) -> EnvironmentClientProtocol:
        return (
            self._client
            if self._client
            else cast(EnvironmentClientProtocol, EnvironmentAPIClient())
        )

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="list_inventory_moves",
            description=(
                "Get inventory movement history. "
                "Use to track inventory movements across locations and time."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "warehouse_id": {
                        "type": "string",
                        "description": "Optional: Filter by warehouse",
                    },
                    "product_id": {"type": "string", "description": "Optional: Filter by product"},
                    "move_type": {
                        "type": "string",
                        "description": "Optional: Filter by move type (e.g., 'adjustment')",
                    },
                    "from_ts": {
                        "type": "string",
                        "description": "Optional: Start timestamp (ISO format)",
                    },
                    "to_ts": {
                        "type": "string",
                        "description": "Optional: End timestamp (ISO format)",
                    },
                },
                "required": [],
            },
            category="environment",
            cache_ttl=CACHE_TTL_HISTORY,
        )

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        async with self.get_client() as client:
            return await client.list_inventory_moves(
                warehouse_id=kwargs.get("warehouse_id"),
                product_id=kwargs.get("product_id"),
                move_type=kwargs.get("move_type"),
                from_ts=kwargs.get("from_ts"),
                to_ts=kwargs.get("to_ts"),
            )


class GetInventoryMoveTool(APIClientTool):
    """Get a single inventory move."""

    def __init__(self, client: EnvironmentClientProtocol | None = None) -> None:
        self._client = client
        super().__init__()

    def get_client(self) -> EnvironmentClientProtocol:
        return (
            self._client
            if self._client
            else cast(EnvironmentClientProtocol, EnvironmentAPIClient())
        )

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="get_inventory_move",
            description="Get detailed information for a specific inventory move.",
            parameters={
                "type": "object",
                "properties": {
                    "move_id": {"type": "string", "description": "Inventory move ID (UUID)"},
                },
                "required": ["move_id"],
            },
            category="environment",
            cache_ttl=CACHE_TTL_HISTORY,
        )

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        self._validate_required_params(["move_id"], kwargs)
        async with self.get_client() as client:
            return await client.get_inventory_move(move_id=kwargs["move_id"])


class GetInventoryMoveAuditTraceTool(APIClientTool):
    """Get the audit chain for a movement (full audit trail reconstruction)."""

    def __init__(self, client: EnvironmentClientProtocol | None = None) -> None:
        self._client = client
        super().__init__()

    def get_client(self) -> EnvironmentClientProtocol:
        return (
            self._client
            if self._client
            else cast(EnvironmentClientProtocol, EnvironmentAPIClient())
        )

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="get_inventory_move_audit_trace",
            description=(
                "Get full audit chain for an inventory movement. "
                "Returns move record and related observations."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "move_id": {"type": "string", "description": "Inventory move ID (UUID)"},
                },
                "required": ["move_id"],
            },
            category="environment",
            cache_ttl=CACHE_TTL_HISTORY,
        )

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        self._validate_required_params(["move_id"], kwargs)
        async with self.get_client() as client:
            return await client.get_inventory_move_audit_trace(move_id=kwargs["move_id"])


class GetInventoryAdjustmentsSummaryTool(APIClientTool):
    """Get aggregated inventory adjustments (investigate discrepancies and shrinkage patterns)."""

    def __init__(self, client: EnvironmentClientProtocol | None = None) -> None:
        self._client = client
        super().__init__()

    def get_client(self) -> EnvironmentClientProtocol:
        return (
            self._client
            if self._client
            else cast(EnvironmentClientProtocol, EnvironmentAPIClient())
        )

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="get_inventory_adjustments_summary",
            description=(
                "Get aggregated inventory adjustments with breakdown by reason code. "
                "Use to investigate discrepancies and shrinkage patterns."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "warehouse_id": {
                        "type": "string",
                        "description": "Optional: Filter by warehouse",
                    },
                    "product_id": {"type": "string", "description": "Optional: Filter by product"},
                    "from_ts": {
                        "type": "string",
                        "description": "Optional: Start timestamp (ISO format)",
                    },
                    "to_ts": {
                        "type": "string",
                        "description": "Optional: End timestamp (ISO format)",
                    },
                },
                "required": [],
            },
            category="environment",
            cache_ttl=CACHE_TTL_ANALYTICS,
        )

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        async with self.get_client() as client:
            return await client.get_inventory_adjustments_summary(
                warehouse_id=kwargs.get("warehouse_id"),
                product_id=kwargs.get("product_id"),
                from_ts=kwargs.get("from_ts"),
                to_ts=kwargs.get("to_ts"),
            )


# ========================================
# TOPOLOGY MODULE (6 tools)
# ========================================


class ListWarehousesTool(APIClientTool):
    """Get list of warehouses."""

    def __init__(self, client: EnvironmentClientProtocol | None = None) -> None:
        self._client = client
        super().__init__()

    def get_client(self) -> EnvironmentClientProtocol:
        return (
            self._client
            if self._client
            else cast(EnvironmentClientProtocol, EnvironmentAPIClient())
        )

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="list_warehouses",
            description="Get list of warehouses with region and timezone information.",
            parameters={
                "type": "object",
                "properties": {
                    "region": {"type": "string", "description": "Optional: Filter by region"},
                },
                "required": [],
            },
            category="environment",
            cache_ttl=CACHE_TTL_ANALYTICS,
        )

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        async with self.get_client() as client:
            return await client.list_warehouses(region=kwargs.get("region"))


class GetWarehouseTool(APIClientTool):
    """Get full warehouse record."""

    def __init__(self, client: EnvironmentClientProtocol | None = None) -> None:
        self._client = client
        super().__init__()

    def get_client(self) -> EnvironmentClientProtocol:
        return (
            self._client
            if self._client
            else cast(EnvironmentClientProtocol, EnvironmentAPIClient())
        )

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="get_warehouse",
            description="Get detailed information for a specific warehouse.",
            parameters={
                "type": "object",
                "properties": {
                    "warehouse_id": {"type": "string", "description": "Warehouse ID (UUID)"},
                },
                "required": ["warehouse_id"],
            },
            category="environment",
            cache_ttl=CACHE_TTL_ANALYTICS,
        )

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        self._validate_required_params(["warehouse_id"], kwargs)
        async with self.get_client() as client:
            return await client.get_warehouse(warehouse_id=kwargs["warehouse_id"])


class ListLocationsTool(APIClientTool):
    """Get flat location structure."""

    def __init__(self, client: EnvironmentClientProtocol | None = None) -> None:
        self._client = client
        super().__init__()

    def get_client(self) -> EnvironmentClientProtocol:
        return (
            self._client
            if self._client
            else cast(EnvironmentClientProtocol, EnvironmentAPIClient())
        )

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="list_locations",
            description=(
                "Get flat list of storage locations within a warehouse. "
                "Use to access location structure."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "warehouse_id": {"type": "string", "description": "Warehouse ID (required)"},
                    "type": {"type": "string", "description": "Optional: Filter by location type"},
                    "parent_location_id": {
                        "type": "string",
                        "description": "Optional: Filter by parent location",
                    },
                    "code_like": {
                        "type": "string",
                        "description": "Optional: Filter by location code pattern",
                    },
                },
                "required": ["warehouse_id"],
            },
            category="environment",
            cache_ttl=CACHE_TTL_ANALYTICS,
        )

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        self._validate_required_params(["warehouse_id"], kwargs)
        async with self.get_client() as client:
            return await client.list_locations(
                warehouse_id=kwargs["warehouse_id"],
                type=kwargs.get("type"),
                parent_location_id=kwargs.get("parent_location_id"),
                code_like=kwargs.get("code_like"),
            )


class GetLocationTool(APIClientTool):
    """Get full location record."""

    def __init__(self, client: EnvironmentClientProtocol | None = None) -> None:
        self._client = client
        super().__init__()

    def get_client(self) -> EnvironmentClientProtocol:
        return (
            self._client
            if self._client
            else cast(EnvironmentClientProtocol, EnvironmentAPIClient())
        )

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="get_location",
            description="Get detailed information for a specific location.",
            parameters={
                "type": "object",
                "properties": {
                    "location_id": {"type": "string", "description": "Location ID (UUID)"},
                },
                "required": ["location_id"],
            },
            category="environment",
            cache_ttl=CACHE_TTL_ANALYTICS,
        )

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        self._validate_required_params(["location_id"], kwargs)
        async with self.get_client() as client:
            return await client.get_location(location_id=kwargs["location_id"])


class GetLocationsTreeTool(APIClientTool):
    """Get hierarchical location tree (warehouse topology reconstruction)."""

    def __init__(self, client: EnvironmentClientProtocol | None = None) -> None:
        self._client = client
        super().__init__()

    def get_client(self) -> EnvironmentClientProtocol:
        return (
            self._client
            if self._client
            else cast(EnvironmentClientProtocol, EnvironmentAPIClient())
        )

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="get_locations_tree",
            description=(
                "Get hierarchical location tree for a warehouse. "
                "Use for warehouse topology reconstruction."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "warehouse_id": {"type": "string", "description": "Warehouse ID (UUID)"},
                },
                "required": ["warehouse_id"],
            },
            category="environment",
            cache_ttl=CACHE_TTL_ANALYTICS,
        )

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        self._validate_required_params(["warehouse_id"], kwargs)
        async with self.get_client() as client:
            return await client.get_locations_tree(warehouse_id=kwargs["warehouse_id"])


class GetCapacityUtilizationSnapshotTool(APIClientTool):
    """Get capacity utilization metrics (for capacity planning and storage pressure analysis)."""

    def __init__(self, client: EnvironmentClientProtocol | None = None) -> None:
        self._client = client
        super().__init__()

    def get_client(self) -> EnvironmentClientProtocol:
        return (
            self._client
            if self._client
            else cast(EnvironmentClientProtocol, EnvironmentAPIClient())
        )

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="get_capacity_utilization_snapshot",
            description=(
                "Get capacity utilization metrics for locations. "
                "Use for capacity planning and storage pressure analysis."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "warehouse_id": {"type": "string", "description": "Warehouse ID (UUID)"},
                    "type": {"type": "string", "description": "Optional: Filter by location type"},
                },
                "required": ["warehouse_id"],
            },
            category="environment",
            cache_ttl=CACHE_TTL_ANALYTICS,
        )

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        self._validate_required_params(["warehouse_id"], kwargs)
        async with self.get_client() as client:
            return await client.get_capacity_utilization_snapshot(
                warehouse_id=kwargs["warehouse_id"],
                type=kwargs.get("type"),
            )


# ========================================
# DEVICE MONITORING MODULE (4 tools)
# ========================================


class ListSensorDevicesTool(APIClientTool):
    """Get list of sensor devices."""

    def __init__(self, client: EnvironmentClientProtocol | None = None) -> None:
        self._client = client
        super().__init__()

    def get_client(self) -> EnvironmentClientProtocol:
        return (
            self._client
            if self._client
            else cast(EnvironmentClientProtocol, EnvironmentAPIClient())
        )

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="list_sensor_devices",
            description="Get list of sensor devices with status, type, and noise characteristics.",
            parameters={
                "type": "object",
                "properties": {
                    "warehouse_id": {
                        "type": "string",
                        "description": "Optional: Filter by warehouse",
                    },
                    "device_type": {
                        "type": "string",
                        "description": "Optional: Filter by device type",
                    },
                    "status": {
                        "type": "string",
                        "description": "Optional: Filter by status (e.g., 'online', 'offline')",
                    },
                },
                "required": [],
            },
            category="environment",
            skip_cache=True,  # Real-time device status
        )

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        async with self.get_client() as client:
            return await client.list_sensor_devices(
                warehouse_id=kwargs.get("warehouse_id"),
                device_type=kwargs.get("device_type"),
                status=kwargs.get("status"),
            )


class GetSensorDeviceTool(APIClientTool):
    """Get full device record."""

    def __init__(self, client: EnvironmentClientProtocol | None = None) -> None:
        self._client = client
        super().__init__()

    def get_client(self) -> EnvironmentClientProtocol:
        return (
            self._client
            if self._client
            else cast(EnvironmentClientProtocol, EnvironmentAPIClient())
        )

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="get_sensor_device",
            description="Get detailed information for a specific sensor device.",
            parameters={
                "type": "object",
                "properties": {
                    "device_id": {"type": "string", "description": "Device ID (UUID)"},
                },
                "required": ["device_id"],
            },
            category="environment",
            skip_cache=True,  # Real-time device status
        )

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        self._validate_required_params(["device_id"], kwargs)
        async with self.get_client() as client:
            return await client.get_sensor_device(device_id=kwargs["device_id"])


class GetDeviceHealthSummaryTool(APIClientTool):
    """Get health metrics for devices (operational health diagnostics)."""

    def __init__(self, client: EnvironmentClientProtocol | None = None) -> None:
        self._client = client
        super().__init__()

    def get_client(self) -> EnvironmentClientProtocol:
        return (
            self._client
            if self._client
            else cast(EnvironmentClientProtocol, EnvironmentAPIClient())
        )

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="get_device_health_summary",
            description=(
                "Get health metrics for devices within time window. "
                "Use for operational health diagnostics."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "warehouse_id": {
                        "type": "string",
                        "description": "Optional: Filter by warehouse",
                    },
                    "since_ts": {
                        "type": "string",
                        "description": "Optional: Start timestamp (ISO format)",
                    },
                    "as_of": {
                        "type": "string",
                        "description": "Optional: End timestamp (ISO format)",
                    },
                },
                "required": [],
            },
            category="environment",
            cache_ttl=300,  # 5 minutes for health metrics
        )

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        async with self.get_client() as client:
            return await client.get_device_health_summary(
                warehouse_id=kwargs.get("warehouse_id"),
                since_ts=kwargs.get("since_ts"),
                as_of=kwargs.get("as_of"),
            )


class GetDeviceAnomaliesTool(APIClientTool):
    """Detect anomalous device behavior (IoT reliability monitoring)."""

    def __init__(self, client: EnvironmentClientProtocol | None = None) -> None:
        self._client = client
        super().__init__()

    def get_client(self) -> EnvironmentClientProtocol:
        return (
            self._client
            if self._client
            else cast(EnvironmentClientProtocol, EnvironmentAPIClient())
        )

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="get_device_anomalies",
            description=(
                "Detect anomalous device behavior (offline but producing, "
                "online but silent, etc.). Use for IoT reliability monitoring."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "warehouse_id": {
                        "type": "string",
                        "description": "Optional: Filter by warehouse",
                    },
                    "window": {
                        "type": "integer",
                        "description": "Optional: Time window in minutes",
                    },
                },
                "required": [],
            },
            category="environment",
            cache_ttl=300,  # 5 minutes for anomaly detection
        )

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        async with self.get_client() as client:
            return await client.get_device_anomalies(
                warehouse_id=kwargs.get("warehouse_id"),
                window=kwargs.get("window"),
            )


# ========================================
# OBSERVED INVENTORY MODULE (1 tool)
# ========================================


class GetObservedInventorySnapshotTool(APIClientTool):
    """Get observed inventory snapshot with quality filtering.

    Returns labeled observations without ground truth.
    """

    def __init__(self, client: EnvironmentClientProtocol | None = None) -> None:
        self._client = client
        super().__init__()

    def get_client(self) -> EnvironmentClientProtocol:
        return (
            self._client
            if self._client
            else cast(EnvironmentClientProtocol, EnvironmentAPIClient())
        )

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="get_observed_inventory_snapshot",
            description=(
                "Get latest observed inventory snapshot with quality status filtering. "
                "Provides labeled observations without leaking true inventory quantities."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "quality_status_in": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Optional: Filter by quality status list " "(e.g., ['good', 'damaged'])"
                        ),
                    },
                },
                "required": [],
            },
            category="environment",
            skip_cache=True,  # Real-time observations
        )

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        async with self.get_client() as client:
            return await client.get_observed_inventory_snapshot(
                quality_status_in=kwargs.get("quality_status_in"),
            )
