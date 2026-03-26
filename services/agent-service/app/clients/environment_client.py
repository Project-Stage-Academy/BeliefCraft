"""
HTTP client for Environment API (warehouse data service).

This client provides typed methods for querying procurement, inventory,
topology, device monitoring, and observed inventory data.

Example:
    ```python
    async with EnvironmentAPIClient() as client:
        suppliers = await client.list_suppliers(region="US")
        moves = await client.list_inventory_moves(product_id="P123")
    ```
"""

from typing import Any, Protocol

from app.clients.base_client import BaseAPIClient
from app.config import get_settings
from common.logging import get_logger

logger = get_logger(__name__)


class EnvironmentClientProtocol(Protocol):
    """
    Protocol defining the interface for Environment API clients.

    This protocol ensures type safety when using EnvironmentAPIClient
    in tools and avoids type: ignore comments.
    """

    async def __aenter__(self) -> "EnvironmentClientProtocol": ...

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None: ...

    # PROCUREMENT MODULE
    async def list_suppliers(
        self,
        region: str | None = None,
        reliability_min: float | None = None,
        name_like: str | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]: ...

    async def get_supplier(
        self, supplier_id: str, timeout: float | None = None
    ) -> dict[str, Any]: ...

    async def list_purchase_orders(
        self,
        supplier_id: str | None = None,
        destination_warehouse_id: str | None = None,
        status_in: list[str] | None = None,
        created_after: str | None = None,
        expected_before: str | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]: ...

    async def get_purchase_order(
        self, purchase_order_id: str, timeout: float | None = None
    ) -> dict[str, Any]: ...

    async def list_po_lines(
        self,
        purchase_order_id: str | None = None,
        purchase_order_ids: list[str] | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]: ...

    async def get_procurement_pipeline_summary(
        self,
        destination_warehouse_id: str | None = None,
        supplier_id: str | None = None,
        status_in: list[str] | None = None,
        horizon_days: int | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]: ...

    # INVENTORY AUDIT MODULE
    async def list_inventory_moves(
        self,
        warehouse_id: str | None = None,
        product_id: str | None = None,
        move_type: str | None = None,
        from_ts: str | None = None,
        to_ts: str | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]: ...

    async def get_inventory_move(
        self, move_id: str, timeout: float | None = None
    ) -> dict[str, Any]: ...

    async def get_inventory_move_audit_trace(
        self, move_id: str, timeout: float | None = None
    ) -> dict[str, Any]: ...

    async def get_inventory_adjustments_summary(
        self,
        warehouse_id: str | None = None,
        product_id: str | None = None,
        from_ts: str | None = None,
        to_ts: str | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]: ...

    # TOPOLOGY MODULE
    async def list_warehouses(
        self, region: str | None = None, timeout: float | None = None
    ) -> dict[str, Any]: ...

    async def get_warehouse(
        self, warehouse_id: str, timeout: float | None = None
    ) -> dict[str, Any]: ...

    async def list_locations(
        self,
        warehouse_id: str,
        type: str | None = None,
        parent_location_id: str | None = None,
        code_like: str | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]: ...

    async def get_location(
        self, location_id: str, timeout: float | None = None
    ) -> dict[str, Any]: ...

    async def get_locations_tree(
        self, warehouse_id: str, timeout: float | None = None
    ) -> dict[str, Any]: ...

    async def get_capacity_utilization_snapshot(
        self,
        warehouse_id: str,
        type: str | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]: ...

    # DEVICE MONITORING MODULE
    async def list_sensor_devices(
        self,
        warehouse_id: str | None = None,
        device_type: str | None = None,
        status: str | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]: ...

    async def get_sensor_device(
        self, device_id: str, timeout: float | None = None
    ) -> dict[str, Any]: ...

    async def get_device_health_summary(
        self,
        warehouse_id: str | None = None,
        since_ts: str | None = None,
        as_of: str | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]: ...

    async def get_device_anomalies(
        self,
        warehouse_id: str | None = None,
        window: int | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]: ...

    # OBSERVED INVENTORY MODULE
    async def get_observed_inventory_snapshot(
        self,
        quality_status_in: list[str] | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]: ...


class EnvironmentAPIClient(BaseAPIClient):
    """
    Client for Environment API (warehouse data).

    Provides methods for:
    - PROCUREMENT: Suppliers, purchase orders, PO lines, pipeline summary
    - INVENTORY AUDIT: Moves, audit trace, adjustments
    - TOPOLOGY: Warehouses, locations, capacity utilization
    - DEVICE MONITORING: Sensor devices, health summary, anomalies
    - OBSERVED INVENTORY: Snapshot with quality filtering
    """

    def __init__(self) -> None:
        """Initialize Environment API client with config from settings."""
        settings = get_settings()
        super().__init__(base_url=settings.ENVIRONMENT_API_URL, service_name="environment-api")

    # ========== PROCUREMENT MODULE ==========

    async def list_suppliers(
        self,
        region: str | None = None,
        reliability_min: float | None = None,
        name_like: str | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Get list of suppliers with reliability and region metadata."""
        params: dict[str, Any] = {}
        if region:
            params["region"] = region
        if reliability_min is not None:
            params["reliability_min"] = reliability_min
        if name_like:
            params["name_like"] = name_like

        return await self.get(
            "/api/v1/smart-query/procurement/suppliers", params=params, timeout=timeout
        )

    async def get_supplier(self, supplier_id: str, timeout: float | None = None) -> dict[str, Any]:
        """Get detailed information for a single supplier."""
        return await self.get(
            f"/api/v1/smart-query/procurement/suppliers/{supplier_id}", timeout=timeout
        )

    async def list_purchase_orders(
        self,
        supplier_id: str | None = None,
        destination_warehouse_id: str | None = None,
        status_in: list[str] | None = None,
        created_after: str | None = None,
        expected_before: str | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Get purchase orders with filtering capabilities."""
        params: dict[str, Any] = {}
        if supplier_id:
            params["supplier_id"] = supplier_id
        if destination_warehouse_id:
            params["destination_warehouse_id"] = destination_warehouse_id
        if status_in:
            params["status_in"] = status_in
        if created_after:
            params["created_after"] = created_after
        if expected_before:
            params["expected_before"] = expected_before

        return await self.get(
            "/api/v1/smart-query/procurement/purchase-orders", params=params, timeout=timeout
        )

    async def get_purchase_order(
        self, purchase_order_id: str, timeout: float | None = None
    ) -> dict[str, Any]:
        """Get a single purchase order."""
        return await self.get(
            f"/api/v1/smart-query/procurement/purchase-orders/{purchase_order_id}",
            timeout=timeout,
        )

    async def list_po_lines(
        self,
        purchase_order_id: str | None = None,
        purchase_order_ids: list[str] | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Get line-level details for purchase orders."""
        params: dict[str, Any] = {}
        if purchase_order_id:
            params["purchase_order_id"] = purchase_order_id
        if purchase_order_ids:
            params["purchase_order_ids"] = ",".join(purchase_order_ids)

        return await self.get(
            "/api/v1/smart-query/procurement/po-lines", params=params, timeout=timeout
        )

    async def get_procurement_pipeline_summary(
        self,
        destination_warehouse_id: str | None = None,
        supplier_id: str | None = None,
        status_in: list[str] | None = None,
        horizon_days: int | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Get aggregated inbound supply pipeline metrics."""
        params: dict[str, Any] = {}
        if destination_warehouse_id:
            params["destination_warehouse_id"] = destination_warehouse_id
        if supplier_id:
            params["supplier_id"] = supplier_id
        if status_in:
            params["status_in"] = status_in
        if horizon_days is not None:
            params["horizon_days"] = horizon_days

        return await self.get(
            "/api/v1/smart-query/procurement/pipeline-summary", params=params, timeout=timeout
        )

    # ========== INVENTORY AUDIT MODULE ==========

    async def list_inventory_moves(
        self,
        warehouse_id: str | None = None,
        product_id: str | None = None,
        move_type: str | None = None,
        from_ts: str | None = None,
        to_ts: str | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Get inventory movement history."""
        params: dict[str, Any] = {}
        if warehouse_id:
            params["warehouse_id"] = warehouse_id
        if product_id:
            params["product_id"] = product_id
        if move_type:
            params["move_type"] = move_type
        if from_ts:
            params["from_ts"] = from_ts
        if to_ts:
            params["to_ts"] = to_ts

        return await self.get("/api/v1/smart-query/inventory/moves", params=params, timeout=timeout)

    async def get_inventory_move(
        self, move_id: str, timeout: float | None = None
    ) -> dict[str, Any]:
        """Get a single inventory move."""
        return await self.get(f"/api/v1/smart-query/inventory/moves/{move_id}", timeout=timeout)

    async def get_inventory_move_audit_trace(
        self, move_id: str, timeout: float | None = None
    ) -> dict[str, Any]:
        """Get the audit chain for a movement."""
        return await self.get(
            f"/api/v1/smart-query/inventory/moves/{move_id}/audit-trace", timeout=timeout
        )

    async def get_inventory_adjustments_summary(
        self,
        warehouse_id: str | None = None,
        product_id: str | None = None,
        from_ts: str | None = None,
        to_ts: str | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Get aggregated inventory adjustments."""
        params: dict[str, Any] = {}
        if warehouse_id:
            params["warehouse_id"] = warehouse_id
        if product_id:
            params["product_id"] = product_id
        if from_ts:
            params["from_ts"] = from_ts
        if to_ts:
            params["to_ts"] = to_ts

        return await self.get(
            "/api/v1/smart-query/inventory/adjustments-summary", params=params, timeout=timeout
        )

    # ========== TOPOLOGY MODULE ==========

    async def list_warehouses(
        self, region: str | None = None, timeout: float | None = None
    ) -> dict[str, Any]:
        """Get list of warehouses."""
        params: dict[str, Any] = {}
        if region:
            params["region"] = region

        return await self.get(
            "/api/v1/smart-query/topology/warehouses", params=params, timeout=timeout
        )

    async def get_warehouse(
        self, warehouse_id: str, timeout: float | None = None
    ) -> dict[str, Any]:
        """Get full warehouse record."""
        return await self.get(
            f"/api/v1/smart-query/topology/warehouses/{warehouse_id}", timeout=timeout
        )

    async def list_locations(
        self,
        warehouse_id: str,
        type: str | None = None,
        parent_location_id: str | None = None,
        code_like: str | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Get flat location structure."""
        params: dict[str, Any] = {"warehouse_id": warehouse_id}
        if type:
            params["type"] = type
        if parent_location_id:
            params["parent_location_id"] = parent_location_id
        if code_like:
            params["code_like"] = code_like

        return await self.get(
            "/api/v1/smart-query/topology/locations", params=params, timeout=timeout
        )

    async def get_location(self, location_id: str, timeout: float | None = None) -> dict[str, Any]:
        """Get full location record."""
        return await self.get(
            f"/api/v1/smart-query/topology/locations/{location_id}", timeout=timeout
        )

    async def get_locations_tree(
        self, warehouse_id: str, timeout: float | None = None
    ) -> dict[str, Any]:
        """Get hierarchical location tree."""
        return await self.get(
            f"/api/v1/smart-query/topology/warehouses/{warehouse_id}/locations-tree",
            timeout=timeout,
        )

    async def get_capacity_utilization_snapshot(
        self,
        warehouse_id: str,
        type: str | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Get capacity utilization metrics."""
        params: dict[str, Any] = {}
        if type:
            params["type"] = type

        return await self.get(
            f"/api/v1/smart-query/topology/warehouses/{warehouse_id}/capacity-utilization",
            params=params,
            timeout=timeout,
        )

    # ========== DEVICE MONITORING MODULE ==========

    async def list_sensor_devices(
        self,
        warehouse_id: str | None = None,
        device_type: str | None = None,
        status: str | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Get list of sensor devices."""
        params: dict[str, Any] = {}
        if warehouse_id:
            params["warehouse_id"] = warehouse_id
        if device_type:
            params["device_type"] = device_type
        if status:
            params["status"] = status

        return await self.get("/api/v1/smart-query/devices", params=params, timeout=timeout)

    async def get_sensor_device(
        self, device_id: str, timeout: float | None = None
    ) -> dict[str, Any]:
        """Get full device record."""
        return await self.get(f"/api/v1/smart-query/devices/{device_id}", timeout=timeout)

    async def get_device_health_summary(
        self,
        warehouse_id: str | None = None,
        since_ts: str | None = None,
        as_of: str | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Get health metrics for devices within time window."""
        params: dict[str, Any] = {}
        if warehouse_id:
            params["warehouse_id"] = warehouse_id
        if since_ts:
            params["since_ts"] = since_ts
        if as_of:
            params["as_of"] = as_of

        return await self.get(
            "/api/v1/smart-query/devices/health-summary", params=params, timeout=timeout
        )

    async def get_device_anomalies(
        self,
        warehouse_id: str | None = None,
        window: int | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Detect anomalous device behavior within a window measured in hours."""
        params: dict[str, Any] = {}
        if warehouse_id:
            params["warehouse_id"] = warehouse_id
        if window is not None:
            params["window"] = window

        return await self.get(
            "/api/v1/smart-query/devices/anomalies", params=params, timeout=timeout
        )

    # ========== OBSERVED INVENTORY MODULE ==========

    async def get_observed_inventory_snapshot(
        self,
        quality_status_in: list[str] | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Get observed inventory snapshot with quality filtering."""
        params: dict[str, Any] = {}
        if quality_status_in:
            params["quality_status_in"] = ",".join(quality_status_in)

        return await self.get(
            "/api/v1/smart-query/inventory/observed-snapshot",
            params=params,
            timeout=timeout,
        )
