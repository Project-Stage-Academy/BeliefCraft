"""
Tools package for agent service.

This package provides the tool system used by ReAct and EnvSubAgent to:
- Query warehouse state (environment tools)
- Retrieve knowledge (RAG tools via MCP server)
- Load domain expertise (skill tools)
- Perform calculations (planning tools)

Registry creation is handled by ToolRegistryFactory, which ensures:
- ReActAgent gets RAG + skill tools only
- EnvSubAgent gets environment tools only

All tools are automatically wrapped with CachedTool for Redis caching.

Cache Strategy:
- Real-time sensors (observations, orders): skip_cache=True
- Shipments: 5 minutes
- Analytics/risk: 10 minutes
- History: 1 hour
- RAG (static knowledge via MCP): 24 hours
- Skills (static expertise): 24 hours

Example:
    ```python
    from app.tools.factory import ToolRegistryFactory

    # Create agent-specific registries
    react_registry = ToolRegistryFactory.create_react_agent_registry()
    env_registry = ToolRegistryFactory.create_env_sub_agent_registry()

    # Register RAG tools from MCP
    await register_mcp_rag_tools(mcp_client, registry=react_registry)

    # Register skill tools
    register_skill_tools(skills_dir, registry=react_registry)
    ```
"""

from app.tools.base import BaseTool, ToolMetadata, ToolResult
from app.tools.cached_tool import CachedTool
from app.tools.factory import ToolRegistryFactory
from app.tools.mcp_tool import MCPClientProtocol
from app.tools.registry import ToolRegistry

__all__ = [
    "BaseTool",
    "ToolMetadata",
    "ToolResult",
    "ToolRegistry",
    "ToolRegistryFactory",
    "CachedTool",
    "MCPClientProtocol",
]
