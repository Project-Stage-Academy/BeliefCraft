"""
HTTP client for Environment API (warehouse data service).

This client provides typed methods for querying warehouse state,
inventory history, order backlogs, and performing risk calculations.

Example:
    ```python
    async with EnvironmentAPIClient() as client:
        obs = await client.get_current_observations(product_id="P123")
        backlog = await client.get_order_backlog(status="pending")
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

    async def get_current_observations(
        self,
        product_id: str | None = None,
        location_id: str | None = None,
        warehouse_id: str | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]: ...

    async def get_inventory_history(
        self, product_id: str, days: int = 30, timeout: float | None = None
    ) -> dict[str, Any]: ...

    async def get_order_backlog(
        self, status: str | None = None, priority: str | None = None
    ) -> dict[str, Any]: ...

    async def get_shipments_in_transit(self, warehouse_id: str | None = None) -> dict[str, Any]: ...

    async def calculate_stockout_probability(self, product_id: str) -> dict[str, Any]: ...

    async def calculate_lead_time_risk(
        self, supplier_id: str | None = None, route_id: str | None = None
    ) -> dict[str, Any]: ...


class EnvironmentAPIClient(BaseAPIClient):
    """
    Client for Environment API (warehouse data).

    Provides methods for:
    - Querying current warehouse observations
    - Retrieving inventory history
    - Getting order backlog information
    - Checking shipments in transit
    - Calculating stockout probabilities
    - Assessing lead time risks
    """

    def __init__(self) -> None:
        """Initialize Environment API client with config from settings."""
        settings = get_settings()
        super().__init__(base_url=settings.ENVIRONMENT_API_URL, service_name="environment-api")

    async def get_current_observations(
        self,
        product_id: str | None = None,
        location_id: str | None = None,
        warehouse_id: str | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """
        Get current warehouse observations (inventory levels, demand, etc.).

        Args:
            product_id: Optional filter by product ID
            location_id: Optional filter by location ID
            warehouse_id: Optional filter by warehouse ID

        Returns:
            Dictionary with current observations data

        Example:
            ```python
            # Get all observations
            obs = await client.get_current_observations()

            # Get observations for specific product
            obs = await client.get_current_observations(product_id="P123")
            ```
        """
        params: dict[str, Any] = {}
        if product_id:
            params["product_id"] = product_id
        if location_id:
            params["location_id"] = location_id
        if warehouse_id:
            params["warehouse_id"] = warehouse_id

        return await self.get("/observations/current", params=params, timeout=timeout)

    async def get_inventory_history(
        self, product_id: str, days: int = 30, timeout: float | None = None
    ) -> dict[str, Any]:
        """
        Get inventory history for a product.

        Args:
            product_id: Product ID to query
            days: Number of days of history (default: 30)

        Returns:
            Dictionary with historical inventory data

        Example:
            ```python
            history = await client.get_inventory_history(
                product_id="P123",
                days=60
            )
            ```
        """
        return await self.get(
            f"/inventory/history/{product_id}", params={"days": days}, timeout=timeout
        )

    async def get_order_backlog(
        self, status: str | None = None, priority: str | None = None
    ) -> dict[str, Any]:
        """
        Get current order backlog.

        Args:
            status: Optional filter by status (e.g., "pending", "processing")
            priority: Optional filter by priority (e.g., "high", "medium", "low")

        Returns:
            Dictionary with order backlog data

        Example:
            ```python
            # All pending orders
            backlog = await client.get_order_backlog(status="pending")

            # High priority orders
            backlog = await client.get_order_backlog(priority="high")
            ```
        """
        params: dict[str, Any] = {}
        if status:
            params["status"] = status
        if priority:
            params["priority"] = priority

        return await self.get("/orders/backlog", params=params)

    async def get_shipments_in_transit(self, warehouse_id: str | None = None) -> dict[str, Any]:
        """
        Get shipments currently in transit.

        Args:
            warehouse_id: Optional filter by destination warehouse

        Returns:
            Dictionary with shipment data

        Example:
            ```python
            shipments = await client.get_shipments_in_transit(
                warehouse_id="WH1"
            )
            ```
        """
        params: dict[str, Any] = {}
        if warehouse_id:
            params["warehouse_id"] = warehouse_id

        return await self.get("/shipments/in-transit", params=params)

    async def calculate_stockout_probability(self, product_id: str) -> dict[str, Any]:
        """
        Calculate stockout probability for a product.

        Uses historical demand patterns and current inventory
        to estimate stockout risk.

        Args:
            product_id: Product ID to analyze

        Returns:
            Dictionary with probability and risk metrics

        Example:
            ```python
            risk = await client.calculate_stockout_probability("P123")
            print(f"Stockout probability: {risk['probability']}")
            ```
        """
        return await self.get(f"/analysis/stockout-probability/{product_id}")

    async def calculate_lead_time_risk(
        self, supplier_id: str | None = None, route_id: str | None = None
    ) -> dict[str, Any]:
        """
        Calculate lead time risk for suppliers/routes.

        Analyzes historical lead time variance and reliability.

        Args:
            supplier_id: Optional filter by supplier
            route_id: Optional filter by shipping route

        Returns:
            Dictionary with lead time statistics and risk metrics

        Example:
            ```python
            # Risk for specific supplier
            risk = await client.calculate_lead_time_risk(
                supplier_id="SUP123"
            )

            # Risk for all suppliers
            risk = await client.calculate_lead_time_risk()
            ```
        """
        params: dict[str, Any] = {}
        if supplier_id:
            params["supplier_id"] = supplier_id
        if route_id:
            params["route_id"] = route_id

        return await self.get("/analysis/lead-time-risk", params=params)
