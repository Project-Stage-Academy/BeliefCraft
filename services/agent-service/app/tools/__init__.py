"""
Tools package for agent service.

This package provides the tool system used by the ReAct agent to:
- Query warehouse state (environment tools)
- Retrieve knowledge (RAG tools via MCP server)
- Perform calculations (planning tools)

Environment tools are automatically registered on import.
RAG tools are loaded dynamically from MCP server during application startup.

All tools are automatically wrapped with CachedTool for Redis caching.

Cache Strategy:
- Real-time sensors (observations, orders): skip_cache=True
- Shipments: 5 minutes
- Analytics/risk: 10 minutes
- History: 1 hour
- RAG (static knowledge via MCP): 24 hours

Example:
    ```python
    from app.tools import tool_registry

    # Environment tools already registered
    # RAG tools registered during startup via register_mcp_rag_tools()

    result = await tool_registry.execute_tool(
        "get_current_observations",
        {"product_id": "P123"}
    )
    ```
"""

from app.tools.base import BaseTool, ToolMetadata, ToolResult
from app.tools.cached_tool import CachedTool

# Import all environment tools (21 total across 5 modules)
from app.tools.environment_tools import (
    GetCapacityUtilizationSnapshotTool,
    GetDeviceAnomaliesTool,
    GetDeviceHealthSummaryTool,
    GetInventoryAdjustmentsSummaryTool,
    GetInventoryMoveAuditTraceTool,
    GetInventoryMoveTool,
    GetLocationsTreeTool,
    GetLocationTool,
    GetObservedInventorySnapshotTool,
    GetProcurementPipelineSummaryTool,
    GetPurchaseOrderTool,
    GetSensorDeviceTool,
    GetSupplierTool,
    GetWarehouseTool,
    ListInventoryMovesTool,
    ListLocationsTool,
    ListPOLinesTool,
    ListPurchaseOrdersTool,
    ListSensorDevicesTool,
    ListSuppliersTool,
    ListWarehousesTool,
)
from app.tools.mcp_loader import MCPToolLoader
from app.tools.mcp_tool import MCPClientProtocol
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
    # MCP
    "MCPClientProtocol",
    "MCPToolLoader",
    # Registration functions
    "register_environment_tools",
    "register_mcp_rag_tools",
]


def register_environment_tools() -> None:
    """
    Register environment tools with caching in the global registry.

    This function registers all 21 warehouse environment tools organized by module:
    - PROCUREMENT MODULE (6): Suppliers, purchase orders, PO lines, pipeline summary
    - INVENTORY AUDIT MODULE (4): Moves, audit trace, adjustments
    - TOPOLOGY MODULE (6): Warehouses, locations, capacity utilization
    - DEVICE MONITORING MODULE (4): Sensor devices, health summary, anomalies
    - OBSERVED INVENTORY MODULE (1): Snapshot with quality filtering

    All tools are wrapped with CachedTool which:
    - Uses TTL from tool metadata (cache_ttl field)
    - Respects skip_cache flag for real-time data (devices, observations)
    - Falls back to global CACHE_TTL_SECONDS if not specified

    Cache Strategy:
    - Real-time data (devices, observations): skip_cache=True
    - Shipments/POs: 5 minutes (CACHE_TTL_SHIPMENTS)
    - Analytics/aggregations: 10 minutes (CACHE_TTL_ANALYTICS)
    - Historical data: 1 hour (CACHE_TTL_HISTORY)
    """
    logger.info("registering_environment_tools_started")

    # PROCUREMENT MODULE (6 tools)
    tool_registry.register(CachedTool(ListSuppliersTool()))
    tool_registry.register(CachedTool(GetSupplierTool()))
    tool_registry.register(CachedTool(ListPurchaseOrdersTool()))
    tool_registry.register(CachedTool(GetPurchaseOrderTool()))
    tool_registry.register(CachedTool(ListPOLinesTool()))
    tool_registry.register(CachedTool(GetProcurementPipelineSummaryTool()))

    # INVENTORY AUDIT MODULE (4 tools)
    tool_registry.register(CachedTool(ListInventoryMovesTool()))
    tool_registry.register(CachedTool(GetInventoryMoveTool()))
    tool_registry.register(CachedTool(GetInventoryMoveAuditTraceTool()))
    tool_registry.register(CachedTool(GetInventoryAdjustmentsSummaryTool()))

    # TOPOLOGY MODULE (6 tools)
    tool_registry.register(CachedTool(ListWarehousesTool()))
    tool_registry.register(CachedTool(GetWarehouseTool()))
    tool_registry.register(CachedTool(ListLocationsTool()))
    tool_registry.register(CachedTool(GetLocationTool()))
    tool_registry.register(CachedTool(GetLocationsTreeTool()))
    tool_registry.register(CachedTool(GetCapacityUtilizationSnapshotTool()))

    # DEVICE MONITORING MODULE (4 tools) - Real-time, skip_cache=True
    tool_registry.register(CachedTool(ListSensorDevicesTool()))
    tool_registry.register(CachedTool(GetSensorDeviceTool()))
    tool_registry.register(CachedTool(GetDeviceHealthSummaryTool()))
    tool_registry.register(CachedTool(GetDeviceAnomaliesTool()))

    # OBSERVED INVENTORY MODULE (1 tool) - Real-time, skip_cache=True
    tool_registry.register(CachedTool(GetObservedInventorySnapshotTool()))

    env_count = sum(
        1 for t in tool_registry.tools.values() if t.get_metadata().category == "environment"
    )

    logger.info(
        "environment_tools_registered",
        count=env_count,
    )


async def register_mcp_rag_tools(mcp_client: MCPClientProtocol) -> None:
    """
    Register RAG tools from MCP server with caching.

    This function:
    1. Uses MCPToolLoader to discover tools from RAG MCP server
    2. Automatically wraps each tool in CachedTool (24 hour TTL)
    3. Registers all discovered tools in the global registry

    RAG tools are expected to include:
    - search_knowledge_base: Semantic search in knowledge base
    - expand_graph_by_ids: Expand knowledge graph from document IDs
    - get_entity_by_number: Retrieve specific entities by number

    Args:
        mcp_client: Connected MCP client for RAG service

    Returns:
        None

    Raises:
        Exception: If MCP server communication fails

    Example:
        ```python
        from app.clients.rag_mcp_client import create_rag_mcp_client
        from app.config import get_settings

        settings = get_settings()
        async with create_rag_mcp_client(settings.RAG_API_URL) as client:
            await register_mcp_rag_tools(client)
        ```
    """
    logger.info("registering_mcp_rag_tools_started")

    # Load tools from MCP server with automatic caching
    loader = MCPToolLoader(
        mcp_client=mcp_client,
        tool_registry=tool_registry,
        wrap_with_cache=True,  # Auto-wrap in CachedTool
        cache_ttl=86400,  # 24 hours for RAG (static knowledge)
        category_override="rag",
    )

    tools_count = await loader.load_tools()

    rag_count = sum(1 for t in tool_registry.tools.values() if t.get_metadata().category == "rag")

    logger.info(
        "mcp_rag_tools_registered",
        discovered=tools_count,
        rag_category_count=rag_count,
        total_tools=len(tool_registry.tools),
    )


# Auto-register environment tools on import (sync)
register_environment_tools()
