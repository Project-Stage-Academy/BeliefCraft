"""
Tools package for agent service.

This package provides the tool system used by the ReAct agent to:
- Query warehouse state (environment tools)
- Retrieve knowledge (RAG tools)
- Perform calculations (planning tools)

Example:
    ```python
    from app.tools import tool_registry, BaseTool, ToolMetadata
    from app.tools.environment_tools import GetInventoryTool

    # Register tools
    tool_registry.register(GetInventoryTool())

    # Execute tool
    result = await tool_registry.execute_tool(
        "get_inventory",
        {"product_id": "P123"}
    )
    ```
"""

from app.tools.base import BaseTool, ToolMetadata, ToolResult
from app.tools.registry import ToolRegistry, tool_registry

__all__ = [
    # Base classes
    "BaseTool",
    "ToolMetadata",
    "ToolResult",
    # Registry
    "ToolRegistry",
    "tool_registry",
]
