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
from app.tools.environment_tools import (
    CalculateLeadTimeRiskTool,
    CalculateStockoutProbabilityTool,
    GetCurrentObservationsTool,
    GetInventoryHistoryTool,
    GetOrderBacklogTool,
    GetShipmentsInTransitTool,
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

    This function registers all warehouse environment tools:
    - Real-time sensor tools (skip_cache=True)
    - Analytics and risk calculation tools (cached)
    - Historical data tools (cached)

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
    """
    logger.info("registering_environment_tools_started")

    # Real-time sensors - skip_cache=True in metadata
    tool_registry.register(CachedTool(GetCurrentObservationsTool()))
    tool_registry.register(CachedTool(GetOrderBacklogTool()))

    # Cached with appropriate TTL from metadata
    tool_registry.register(CachedTool(GetShipmentsInTransitTool()))  # 5 min
    tool_registry.register(CachedTool(CalculateStockoutProbabilityTool()))  # 10 min
    tool_registry.register(CachedTool(CalculateLeadTimeRiskTool()))  # 10 min
    tool_registry.register(CachedTool(GetInventoryHistoryTool()))  # 1 hour

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
