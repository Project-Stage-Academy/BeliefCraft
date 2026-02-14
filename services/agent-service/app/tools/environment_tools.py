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

from typing import Any

from app.clients.environment_client import EnvironmentAPIClient
from app.tools.base import BaseTool, ToolMetadata


class GetCurrentObservationsTool(BaseTool):
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
        )

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        """
        Execute tool to get current observations.

        Args:
            **kwargs: Optional filters (product_id, location_id, warehouse_id)

        Returns:
            Dictionary with current observations data from Environment API
        """
        async with EnvironmentAPIClient() as client:
            result = await client.get_current_observations(  # type: ignore[attr-defined]
                product_id=kwargs.get("product_id"),
                location_id=kwargs.get("location_id"),
                warehouse_id=kwargs.get("warehouse_id"),
            )
        return result  # type: ignore[no-any-return]


class GetOrderBacklogTool(BaseTool):
    """
    Tool to retrieve current order backlog.

    Queries unfulfilled orders with their deadlines, priorities, and statuses.
    Essential for identifying at-risk orders and prioritizing fulfillment.

    Use Cases:
    - Identifying orders at risk of missing deadlines
    - Prioritizing order fulfillment based on urgency
    - Assessing warehouse capacity vs. demand
    """

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
        )

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        """
        Execute tool to get order backlog.

        Args:
            **kwargs: Optional filters (status, priority)

        Returns:
            Dictionary with order backlog data from Environment API
        """
        async with EnvironmentAPIClient() as client:
            result = await client.get_order_backlog(  # type: ignore[attr-defined]
                status=kwargs.get("status"),
                priority=kwargs.get("priority"),
            )
        return result  # type: ignore[no-any-return]


class GetShipmentsInTransitTool(BaseTool):
    """
    Tool to retrieve shipments currently in transit.

    Queries inbound shipments, outbound deliveries, and inter-warehouse transfers
    that are currently in transit. Essential for assessing incoming inventory.

    Use Cases:
    - Forecasting inventory arrivals
    - Assessing delivery risks and delays
    - Planning for incoming inventory capacity
    """

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
        )

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        """
        Execute tool to get shipments in transit.

        Args:
            **kwargs: Optional filter (warehouse_id)

        Returns:
            Dictionary with shipment data from Environment API
        """
        async with EnvironmentAPIClient() as client:
            result = await client.get_shipments_in_transit(  # type: ignore[attr-defined]
                warehouse_id=kwargs.get("warehouse_id")
            )
        return result  # type: ignore[no-any-return]


class CalculateStockoutProbabilityTool(BaseTool):
    """
    Tool to calculate stockout probability for a product.

    Analyzes current inventory, demand forecasts, and lead time uncertainty
    to estimate the probability of stockout. Returns probability value [0, 1].

    Use Cases:
    - Identifying high-risk products needing reorder
    - Prioritizing inventory replenishment
    - Assessing inventory policy effectiveness
    """

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
        )

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        """
        Execute tool to calculate stockout probability.

        Args:
            **kwargs: Must include product_id (str)

        Returns:
            Dictionary with probability and risk metrics from Environment API
        """
        product_id = kwargs["product_id"]
        async with EnvironmentAPIClient() as client:
            result = await client.calculate_stockout_probability(  # type: ignore[attr-defined]
                product_id=product_id
            )
        return result  # type: ignore[no-any-return]


class CalculateLeadTimeRiskTool(BaseTool):
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
        )

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        """
        Execute tool to calculate lead time risk.

        Args:
            **kwargs: Optional filters (supplier_id, route_id)

        Returns:
            Dictionary with lead time statistics and risk metrics from Environment API
        """
        async with EnvironmentAPIClient() as client:
            result = await client.calculate_lead_time_risk(  # type: ignore[attr-defined]
                supplier_id=kwargs.get("supplier_id"),
                route_id=kwargs.get("route_id"),
            )
        return result  # type: ignore[no-any-return]


class GetInventoryHistoryTool(BaseTool):
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
        )

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        """
        Execute tool to get inventory history.

        Args:
            **kwargs: Must include product_id (str), optional days (int, default: 30)

        Returns:
            Dictionary with historical inventory data from Environment API
        """
        product_id = kwargs["product_id"]
        days = kwargs.get("days", 30)
        async with EnvironmentAPIClient() as client:
            result = await client.get_inventory_history(  # type: ignore[attr-defined]
                product_id=product_id, days=days
            )
        return result  # type: ignore[no-any-return]
