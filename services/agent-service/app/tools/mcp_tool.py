"""
Dynamic tool wrapper for MCP server tools.

This module provides MCPTool - a dynamic wrapper that adapts
any MCP server tool to our BaseTool interface following SOLID principles:

- Single Responsibility: MCPTool only wraps and adapts MCP tools
- Open/Closed: MCPTool extends BaseTool without modifying it
- Liskov Substitution: MCPTool is a proper BaseTool replacement
- Interface Segregation: Minimal dependencies on MCP client (Any protocol)
- Dependency Inversion: Depends on abstract MCP client interface
"""

from typing import Any, Protocol, cast

from app.tools.base import BaseTool, ToolMetadata
from common.logging import get_logger

logger = get_logger(__name__)


class MCPClientProtocol(Protocol):
    """Protocol defining MCP client interface for type safety."""

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        """Execute tool on MCP server."""
        ...

    async def list_tools(self) -> list[dict[str, Any]]:
        """List available tools from MCP server."""
        ...


class MCPTool(BaseTool):
    """
    Dynamic wrapper that adapts MCP server tools to BaseTool interface.

    This class wraps tools from any MCP server, allowing them to be used
    within our tool registry and ReAct agent system. It provides:
    - Metadata adaptation from MCP schema to our ToolMetadata format
    - Dynamic tool execution through MCP client
    - Consistent error handling and logging
    """

    def __init__(
        self,
        mcp_client: MCPClientProtocol,
        tool_name: str,
        tool_description: str,
        tool_parameters: dict[str, Any],
        category: str = "mcp",
    ) -> None:
        """
        Initialize dynamic MCP tool wrapper.

        Args:
            mcp_client: MCP client instance for executing tools
            tool_name: Name of the tool from MCP server
            tool_description: Description from MCP server
            tool_parameters: JSON schema for parameters from MCP server
            category: Tool category for organization (default: "mcp")

        Raises:
            ValueError: If tool_name or tool_description is empty
        """
        if not tool_name or not isinstance(tool_name, str):
            raise ValueError("tool_name must be a non-empty string")
        if not tool_description or not isinstance(tool_description, str):
            raise ValueError("tool_description must be a non-empty string")
        if not isinstance(tool_parameters, dict):
            raise ValueError("tool_parameters must be a dictionary")

        self.mcp_client = mcp_client
        self._tool_name = tool_name
        self._tool_description = tool_description
        self._tool_parameters = tool_parameters
        self._category = category
        super().__init__()

    def get_metadata(self) -> ToolMetadata:
        """
        Return metadata adapted from MCP tool schema.

        Returns:
            ToolMetadata with name, description, parameters, and category
        """
        return ToolMetadata(
            name=self._tool_name,
            description=self._tool_description,
            parameters=self._tool_parameters,
            category=self._category,
        )

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        """
        Execute the MCP tool with given arguments.

        Args:
            **kwargs: Tool arguments matching the MCP tool schema

        Returns:
            Result from MCP tool execution

        Raises:
            Exception: If MCP server call fails (propagated from MCP client)
        """
        logger.debug(
            "executing_mcp_tool",
            tool=self._tool_name,
            arguments=kwargs,
        )

        # Call MCP server tool
        result = await self.mcp_client.call_tool(
            name=self._tool_name,
            arguments=kwargs,
        )

        logger.debug(
            "mcp_tool_executed",
            tool=self._tool_name,
            result_type=type(result).__name__,
        )

        # Cast result to expected return type
        return cast(dict[str, Any], result)
