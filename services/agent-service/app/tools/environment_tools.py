"""
Environment tools for querying warehouse state and performing risk analysis.

This module provides tools that allow the ReAct agent to:
- Query current warehouse observations (inventory levels, locations)
- Retrieve inventory history and trends
- Get order backlog information
- Check shipments in transit
- Calculate stockout probabilities
- Assess lead time risks
- Analyze supply chain uncertainties

All tools use EnvironmentAPIClient to communicate with the Environment API
service with automatic retry logic and error handling.

Example:
    ```python
    from app.tools.environment_tools import GetCurrentObservationsTool
    from app.tools.registry import tool_registry

    # Register tool
    tool = GetCurrentObservationsTool()
    tool_registry.register(tool)

    # Execute tool
    result = await tool_registry.execute_tool(
        "get_current_observations",
        {"product_id": "P123"}
    )
    ```
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


class GetCurrentObservationsTool(APIClientTool):
    """
    Tool to retrieve current warehouse observations.

    Queries the Environment API for current inventory levels, sensor readings,
    and warehouse state. Note that observations may be noisy or incomplete
    (sensor errors, delayed updates).

    Use Cases:
    - Understanding current inventory levels across locations
    - Checking real-time warehouse state before decisions
    - Identifying discrepancies between expected and observed inventory
    """

    def __init__(self, client: EnvironmentClientProtocol | None = None) -> None:
        """Initialize tool with optional client for dependency injection."""
        self._client = client
        super().__init__()

    def get_client(self) -> EnvironmentClientProtocol:
        """Get Environment API client instance."""
        return (
            self._client
            if self._client is not None
            else cast(EnvironmentClientProtocol, EnvironmentAPIClient())
        )

    def get_metadata(self) -> ToolMetadata:
        """Return tool metadata with OpenAI function calling schema."""
        return ToolMetadata(
            name="get_current_observations",
            description=(
                "Get current inventory observations from warehouse sensors. "
                "Note: observations may be noisy or incomplete. "
                "Use this to understand current warehouse state. "
                "Optionally filter by product_id, location_id, or warehouse_id."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "product_id": {
                        "type": "string",
                        "description": "Optional: Filter by specific product UUID",
                    },
                    "location_id": {
                        "type": "string",
                        "description": "Optional: Filter by specific location UUID",
                    },
                    "warehouse_id": {
                        "type": "string",
                        "description": "Optional: Filter by specific warehouse UUID",
                    },
                },
                "required": [],
            },
            category="environment",
            skip_cache=True,  # Real-time sensor data - must be fresh
        )

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        """
        Execute tool to get current observations.

        Args:
            **kwargs: Optional filters (product_id, location_id, warehouse_id)

        Returns:
            Dictionary with current observations data from Environment API
        """
        async with self.get_client() as client:
            return await client.get_current_observations(
                product_id=kwargs.get("product_id"),
                location_id=kwargs.get("location_id"),
                warehouse_id=kwargs.get("warehouse_id"),
            )


class GetOrderBacklogTool(APIClientTool):
    """
    Tool to retrieve current order backlog.

    Queries unfulfilled orders with their deadlines, priorities, and statuses.
    Essential for identifying at-risk orders and prioritizing fulfillment.

    Use Cases:
    - Identifying orders at risk of missing deadlines
    - Prioritizing order fulfillment based on urgency
    - Assessing warehouse capacity vs. demand
    """

    def __init__(self, client: EnvironmentClientProtocol | None = None) -> None:
        """Initialize tool with optional client for dependency injection."""
        self._client = client
        super().__init__()

    def get_client(self) -> EnvironmentClientProtocol:
        """Get Environment API client instance."""
        return (
            self._client
            if self._client is not None
            else cast(EnvironmentClientProtocol, EnvironmentAPIClient())
        )

    def get_metadata(self) -> ToolMetadata:
        """Return tool metadata with OpenAI function calling schema."""
        return ToolMetadata(
            name="get_order_backlog",
            description=(
                "Get current unfulfilled orders with deadlines and priorities. "
                "Use this to identify at-risk orders and prioritize fulfillment. "
                "Optionally filter by status or priority level."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["pending", "processing", "at_risk"],
                        "description": "Optional: Filter by order status",
                    },
                    "priority": {
                        "type": "string",
                        "enum": ["low", "medium", "high", "critical"],
                        "description": "Optional: Filter by priority level",
                    },
                },
                "required": [],
            },
            category="environment",
            skip_cache=True,  # Real-time order status - must be fresh
        )

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        """
        Execute tool to get order backlog.

        Args:
            **kwargs: Optional filters (status, priority)

        Returns:
            Dictionary with order backlog data from Environment API
        """
        async with self.get_client() as client:
            return await client.get_order_backlog(
                status=kwargs.get("status"),
                priority=kwargs.get("priority"),
            )


class GetShipmentsInTransitTool(APIClientTool):
    """
    Tool to retrieve shipments currently in transit.

    Queries inbound shipments, outbound deliveries, and inter-warehouse transfers
    that are currently in transit. Essential for assessing incoming inventory.

    Use Cases:
    - Forecasting inventory arrivals
    - Assessing delivery risks and delays
    - Planning for incoming inventory capacity
    """

    def __init__(self, client: EnvironmentClientProtocol | None = None) -> None:
        """Initialize tool with optional client for dependency injection."""
        self._client = client
        super().__init__()

    def get_client(self) -> EnvironmentClientProtocol:
        """Get Environment API client instance."""
        return (
            self._client
            if self._client is not None
            else cast(EnvironmentClientProtocol, EnvironmentAPIClient())
        )

    def get_metadata(self) -> ToolMetadata:
        """Return tool metadata with OpenAI function calling schema."""
        return ToolMetadata(
            name="get_shipments_in_transit",
            description=(
                "Get shipments currently in transit (inbound/outbound/transfer). "
                "Use this to assess incoming inventory and delivery risks. "
                "Optionally filter by destination warehouse_id."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "warehouse_id": {
                        "type": "string",
                        "description": "Optional: Filter by destination warehouse UUID",
                    },
                },
                "required": [],
            },
            category="environment",
            cache_ttl=CACHE_TTL_SHIPMENTS,  # 5 minutes - shipments change slowly
        )

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        """
        Execute tool to get shipments in transit.

        Args:
            **kwargs: Optional filter (warehouse_id)

        Returns:
            Dictionary with shipment data from Environment API
        """
        async with self.get_client() as client:
            return await client.get_shipments_in_transit(warehouse_id=kwargs.get("warehouse_id"))


class CalculateStockoutProbabilityTool(APIClientTool):
    """
    Tool to calculate stockout probability for a product.

    Analyzes current inventory, demand forecasts, and lead time uncertainty
    to estimate the probability of stockout. Returns probability value [0, 1].

    Use Cases:
    - Identifying high-risk products needing reorder
    - Prioritizing inventory replenishment
    - Assessing inventory policy effectiveness
    """

    def __init__(self, client: EnvironmentClientProtocol | None = None) -> None:
        """Initialize tool with optional client for dependency injection."""
        self._client = client
        super().__init__()

    def get_client(self) -> EnvironmentClientProtocol:
        """Get Environment API client instance."""
        return (
            self._client
            if self._client is not None
            else cast(EnvironmentClientProtocol, EnvironmentAPIClient())
        )

    def get_metadata(self) -> ToolMetadata:
        """Return tool metadata with OpenAI function calling schema."""
        return ToolMetadata(
            name="calculate_stockout_probability",
            description=(
                "Calculate the probability that a product will stock out "
                "based on current inventory, demand forecast, and lead times. "
                "Returns probability value between 0 and 1. "
                "Higher values indicate higher stockout risk."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "product_id": {
                        "type": "string",
                        "description": "Product UUID to analyze for stockout risk",
                    },
                },
                "required": ["product_id"],
            },
            category="environment",
            cache_ttl=CACHE_TTL_ANALYTICS,  # 10 minutes - analytics don't change rapidly
        )

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        """
        Execute tool to calculate stockout probability.

        Args:
            **kwargs: Must include product_id (str)

        Returns:
            Dictionary with probability and risk metrics from Environment API

        Raises:
            ValueError: If product_id is missing
        """
        self._validate_required_params(["product_id"], kwargs)
        product_id = kwargs["product_id"]

        async with self.get_client() as client:
            return await client.calculate_stockout_probability(product_id=product_id)


class CalculateLeadTimeRiskTool(APIClientTool):
    """
    Tool to calculate lead time risk (tail risk, CVaR).

    Analyzes historical lead time distributions for suppliers and shipping routes
    to assess delivery risk. Useful for understanding supply chain uncertainty.

    Use Cases:
    - Assessing supplier reliability
    - Identifying high-risk shipping routes
    - Planning safety stock levels
    - CVaR (Conditional Value at Risk) analysis
    """

    def __init__(self, client: EnvironmentClientProtocol | None = None) -> None:
        """Initialize tool with optional client for dependency injection."""
        self._client = client
        super().__init__()

    def get_client(self) -> EnvironmentClientProtocol:
        """Get Environment API client instance."""
        return (
            self._client
            if self._client is not None
            else cast(EnvironmentClientProtocol, EnvironmentAPIClient())
        )

    def get_metadata(self) -> ToolMetadata:
        """Return tool metadata with OpenAI function calling schema."""
        return ToolMetadata(
            name="calculate_lead_time_risk",
            description=(
                "Calculate lead time risk (CVaR, tail risk) for suppliers/routes. "
                "Analyzes historical lead time variance and reliability. "
                "Use this to assess delivery delay probability and plan safety stock. "
                "Optionally filter by supplier_id or route_id."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "supplier_id": {
                        "type": "string",
                        "description": "Optional: Filter by specific supplier UUID",
                    },
                    "route_id": {
                        "type": "string",
                        "description": "Optional: Filter by specific shipping route UUID",
                    },
                },
                "required": [],
            },
            category="environment",
            cache_ttl=CACHE_TTL_ANALYTICS,  # 10 minutes - risk metrics are semi-stable
        )

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        """
        Execute tool to calculate lead time risk.

        Args:
            **kwargs: Optional filters (supplier_id, route_id)

        Returns:
            Dictionary with lead time statistics and risk metrics from Environment API
        """
        async with self.get_client() as client:
            return await client.calculate_lead_time_risk(
                supplier_id=kwargs.get("supplier_id"),
                route_id=kwargs.get("route_id"),
            )


class GetInventoryHistoryTool(APIClientTool):
    """
    Tool to get historical inventory data.

    Retrieves historical inventory levels and movements for trend analysis,
    seasonality detection, and demand pattern understanding.

    Use Cases:
    - Analyzing inventory trends and seasonality
    - Understanding demand patterns
    - Validating forecasting models
    - Historical comparison for decision-making
    """

    def __init__(self, client: EnvironmentClientProtocol | None = None) -> None:
        """Initialize tool with optional client for dependency injection."""
        self._client = client
        super().__init__()

    def get_client(self) -> EnvironmentClientProtocol:
        """Get Environment API client instance."""
        return (
            self._client
            if self._client is not None
            else cast(EnvironmentClientProtocol, EnvironmentAPIClient())
        )

    def get_metadata(self) -> ToolMetadata:
        """Return tool metadata with OpenAI function calling schema."""
        return ToolMetadata(
            name="get_inventory_history",
            description=(
                "Get historical inventory levels and movements for a product. "
                "Use this to analyze trends, seasonality, and demand patterns. "
                "Specify number of days to look back (default: 30, max: 365)."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "product_id": {
                        "type": "string",
                        "description": "Product UUID to retrieve history for",
                    },
                    "days": {
                        "type": "integer",
                        "description": "Number of days to look back (default: 30)",
                        "minimum": 1,
                        "maximum": 365,
                        "default": 30,
                    },
                },
                "required": ["product_id"],
            },
            category="environment",
            cache_ttl=CACHE_TTL_HISTORY,  # 1 hour - historical data doesn't change
        )

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        """
        Execute tool to get inventory history.

        Args:
            **kwargs: Must include product_id (str), optional days (int, default: 30)

        Returns:
            Dictionary with historical inventory data from Environment API

        Raises:
            ValueError: If product_id is missing or days is invalid
        """
        self._validate_required_params(["product_id"], kwargs)

        product_id = kwargs["product_id"]
        if not isinstance(product_id, str) or not product_id.strip():
            raise ValueError("product_id must be a non-empty string")

        days = kwargs.get("days", 30)
        if not isinstance(days, int) or days < 1 or days > 365:
            raise ValueError("days must be an integer between 1 and 365")

        async with self.get_client() as client:
            return await client.get_inventory_history(product_id=product_id, days=days)
