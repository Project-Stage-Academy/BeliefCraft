"""
Tools package for agent service.

This package provides the tool system used by the ReAct agent to:
- Query warehouse state (environment tools)
- Retrieve knowledge (RAG tools)
- Perform calculations (planning tools)

All tools are automatically wrapped with CachedTool for Redis caching
and registered in the global tool_registry on import.

Cache Strategy:
- Real-time sensors (observations, orders): skip_cache=True
- Shipments: 5 minutes
- Analytics/risk: 10 minutes
- History: 1 hour
- RAG (static knowledge): 24 hours

Example:
    ```python
    from app.tools import tool_registry

    # Tools are already registered
    result = await tool_registry.execute_tool(
        "get_current_observations",
        {"product_id": "P123"}
    )
    ```
"""

from app.tools.base import BaseTool, ToolMetadata, ToolResult
from app.tools.cached_tool import CachedTool
from app.tools.environment_tools import (
    CalculateLeadTimeRiskTool,
    CalculateStockoutProbabilityTool,
    GetCurrentObservationsTool,
    GetInventoryHistoryTool,
    GetOrderBacklogTool,
    GetShipmentsInTransitTool,
)
from app.tools.rag_tools import (
    ExpandGraphByIdsTool,
    GetEntityByNumberTool,
    SearchKnowledgeBaseTool,
)
from app.tools.registry import ToolRegistry, tool_registry
from common.logging import get_logger

logger = get_logger(__name__)

__all__ = [
    # Base classes
    "BaseTool",
    "ToolMetadata",
    "ToolResult",
    # Registry
    "ToolRegistry",
    "tool_registry",
    # Caching
    "CachedTool",
    # Registration function
    "register_all_tools",
]


def register_all_tools() -> None:
    """
    Register all tools with caching in the global registry.

    All tools are wrapped with CachedTool which:
    - Uses TTL from tool metadata (cache_ttl field)
    - Respects skip_cache flag for real-time sensors
    - Falls back to global CACHE_TTL_SECONDS if not specified

    Cache Strategy:
    - GetCurrentObservationsTool: skip_cache=True (real-time sensors)
    - GetOrderBacklogTool: skip_cache=True (real-time orders)
    - GetShipmentsInTransitTool: 5 minutes
    - CalculateStockoutProbabilityTool: 10 minutes
    - CalculateLeadTimeRiskTool: 10 minutes
    - GetInventoryHistoryTool: 1 hour
    - SearchKnowledgeBaseTool: 24 hours
    - ExpandGraphByIdsTool: 24 hours
    - GetEntityByNumberTool: 24 hours
    """
    logger.info("registering_all_tools", tool_count=9)

    # Environment Tools (6 tools)
    # Real-time sensors - skip_cache=True in metadata
    tool_registry.register(CachedTool(GetCurrentObservationsTool()))
    tool_registry.register(CachedTool(GetOrderBacklogTool()))

    # Cached with appropriate TTL from metadata
    tool_registry.register(CachedTool(GetShipmentsInTransitTool()))  # 5 min
    tool_registry.register(CachedTool(CalculateStockoutProbabilityTool()))  # 10 min
    tool_registry.register(CachedTool(CalculateLeadTimeRiskTool()))  # 10 min
    tool_registry.register(CachedTool(GetInventoryHistoryTool()))  # 1 hour

    # RAG Tools (3 tools) - all 24 hours from metadata
    tool_registry.register(CachedTool(SearchKnowledgeBaseTool()))
    tool_registry.register(CachedTool(ExpandGraphByIdsTool()))
    tool_registry.register(CachedTool(GetEntityByNumberTool()))

    logger.info(
        "tools_registered_successfully",
        total_tools=len(tool_registry.tools),
        categories={
            "environment": 6,
            "rag": 3,
        },
    )


# Auto-register all tools on import
register_all_tools()
