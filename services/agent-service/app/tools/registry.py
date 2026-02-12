"""
Tool registry for managing agent tools.

This module provides a central registry where all tools are registered
and can be discovered, filtered, and executed by the agent.

Example:
    ```python
    from app.tools.registry import tool_registry
    from app.tools.my_tool import MyTool
    
    # Register tool
    tool = MyTool()
    tool_registry.register(tool)
    
    # Execute tool
    result = await tool_registry.execute_tool(
        "my_tool",
        {"param1": "value"}
    )
    
    # Get OpenAI function schemas
    functions = tool_registry.get_openai_functions(
        categories=["environment", "rag"]
    )
    ```
"""

from typing import Any

from common.logging import get_logger

from app.core.exceptions import ToolExecutionError
from app.tools.base import BaseTool, ToolResult

logger = get_logger(__name__)


class ToolRegistry:
    """
    Central registry for all agent tools.
    
    The registry provides:
    - Tool registration and discovery
    - Category-based filtering
    - Execution wrapper
    - OpenAI function schema generation
    
    Thread-safe for read operations (tool lookup/execution).
    Registration should happen at startup before concurrent access.
    """
    
    def __init__(self) -> None:
        """Initialize empty registry."""
        self._tools: dict[str, BaseTool] = {}
        logger.debug("tool_registry_initialized")
    
    def register(self, tool: BaseTool) -> None:
        """
        Register a tool in the registry.
        
        Args:
            tool: Tool instance to register
        
        Raises:
            ValueError: If tool with same name already registered
        """
        tool_name = tool.metadata.name
        
        if tool_name in self._tools:
            raise ValueError(
                f"Tool '{tool_name}' already registered. "
                f"Each tool must have a unique name."
            )
        
        self._tools[tool_name] = tool
        
        logger.info(
            "tool_registered",
            tool=tool_name,
            category=tool.metadata.category,
            description=tool.metadata.description
        )
    
    def get_tool(self, name: str) -> BaseTool:
        """
        Get a tool by name.
        
        Args:
            name: Tool name (must match metadata.name)
        
        Returns:
            BaseTool instance
        
        Raises:
            ToolExecutionError: If tool not found
        """
        if name not in self._tools:
            available_tools = ", ".join(self._tools.keys())
            raise ToolExecutionError(
                f"Tool '{name}' not found in registry. "
                f"Available tools: {available_tools}",
                tool_name=name
            )
        
        return self._tools[name]
    
    def list_tools(self, category: str | None = None) -> list[BaseTool]:
        """
        List all tools, optionally filtered by category.
        
        Args:
            category: Optional category filter (environment/rag/planning/utility)
        
        Returns:
            List of matching tools
        """
        tools = list(self._tools.values())
        
        if category:
            tools = [t for t in tools if t.metadata.category == category]
            logger.debug(
                "tools_filtered_by_category",
                category=category,
                count=len(tools)
            )
        
        return tools
    
    def get_tool_names(self, category: str | None = None) -> list[str]:
        """
        Get list of tool names, optionally filtered by category.
        
        Args:
            category: Optional category filter
        
        Returns:
            List of tool names
        """
        tools = self.list_tools(category=category)
        return [t.metadata.name for t in tools]
    
    def get_openai_functions(
        self,
        categories: list[str] | None = None
    ) -> list[dict[str, Any]]:
        """
        Get OpenAI function calling schemas for tools.
        
        This generates schemas compatible with:
        - OpenAI GPT-4 function calling
        - Amazon Bedrock Claude function calling
        - Azure OpenAI function calling
        
        Args:
            categories: Optional list of categories to include
                       If None, includes all tools
        
        Returns:
            List of OpenAI function schemas
        
        Example:
            ```python
            # Get all environment and RAG tools
            functions = registry.get_openai_functions(
                categories=["environment", "rag"]
            )
            
            # Use with OpenAI API
            response = openai.chat.completions.create(
                model="gpt-4",
                messages=[...],
                functions=functions
            )
            ```
        """
        tools = list(self._tools.values())
        
        if categories:
            tools = [t for t in tools if t.metadata.category in categories]
            logger.debug(
                "openai_functions_filtered",
                categories=categories,
                tool_count=len(tools)
            )
        
        return [tool.to_openai_function() for tool in tools]
    
    async def execute_tool(
        self,
        name: str,
        arguments: dict[str, Any]
    ) -> ToolResult:
        """
        Execute a tool by name with given arguments.
        
        This is the main entry point for tool execution from the agent.
        It handles tool lookup, execution, and error wrapping.
        
        Args:
            name: Tool name to execute
            arguments: Dictionary of arguments matching tool's parameter schema
        
        Returns:
            ToolResult with success status and data/error
        
        Example:
            ```python
            result = await registry.execute_tool(
                "get_inventory",
                {"product_id": "P123", "location_id": "WH1"}
            )
            
            if result.success:
                print(f"Data: {result.data}")
            else:
                print(f"Error: {result.error}")
            ```
        """
        logger.debug(
            "tool_execution_requested",
            tool=name,
            arguments=arguments
        )
        
        tool = self.get_tool(name)
        return await tool.run(**arguments)
    
    def get_registry_stats(self) -> dict[str, Any]:
        """
        Get statistics about registered tools.
        
        Returns:
            Dictionary with tool counts by category
        """
        stats = {
            "total_tools": len(self._tools),
            "by_category": {}
        }
        
        for tool in self._tools.values():
            category = tool.metadata.category
            stats["by_category"][category] = stats["by_category"].get(category, 0) + 1
        
        return stats


# Global registry instance
# Import this singleton in other modules
tool_registry = ToolRegistry()

