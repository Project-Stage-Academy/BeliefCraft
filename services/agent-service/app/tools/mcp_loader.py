"""
MCP tool loader for dynamic tool autodiscovery.

This module provides MCPToolLoader for automatically discovering tools
from MCP servers and registering them in the tool registry.

SOLID principles applied:
- Single Responsibility: MCPToolLoader only handles MCP tool discovery/registration
- Open/Closed: Can be extended for different MCP server types
- Liskov Substitution: Consistent interface for tool loading
- Interface Segregation: Depends on minimal MCPClient interface
- Dependency Inversion: Injected dependencies (client, registry)
"""

from typing import Any

from app.tools.mcp_tool import MCPClientProtocol, MCPTool
from app.tools.registry import ToolRegistry
from common.logging import get_logger

logger = get_logger(__name__)


class MCPToolLoader:
    """
    Dynamically discovers and registers tools from MCP servers.

    This class handles the tool discovery workflow:
    1. Connect to MCP server
    2. List available tools
    3. Create MCPTool wrappers for each tool
    4. Register tools in the tool registry
    """

    def __init__(
        self,
        mcp_client: MCPClientProtocol,
        tool_registry: ToolRegistry,
    ) -> None:
        """
        Initialize MCP tool loader with dependencies.

        Args:
            mcp_client: MCP client for communicating with server
            tool_registry: Registry to register discovered tools in

        Raises:
            ValueError: If dependencies are invalid
        """
        if mcp_client is None:
            raise ValueError("mcp_client cannot be None")
        if tool_registry is None:
            raise ValueError("tool_registry cannot be None")

        self.mcp_client = mcp_client
        self.tool_registry = tool_registry

    async def load_tools(self) -> int:
        """
        Discover tools from MCP server and register them.

        Returns:
            Number of tools successfully loaded and registered

        Raises:
            Exception: If MCP server communication fails
        """
        logger.info("loading_mcp_tools", starting=True)

        try:
            # Get list of available tools from MCP server
            tools_list = await self.mcp_client.list_tools()

            if not isinstance(tools_list, list):
                logger.warning(
                    "invalid_tools_list",
                    tools_list_type=type(tools_list).__name__,
                )
                return 0

            registered_count = 0

            for tool_schema in tools_list:
                try:
                    # Extract tool metadata from MCP schema
                    tool_name = tool_schema.get("name")
                    tool_description = tool_schema.get("description", "")
                    tool_parameters = tool_schema.get("inputSchema", {})

                    # Validate required fields
                    if not tool_name:
                        logger.warning(
                            "skipping_tool_missing_name",
                            tool_schema=tool_schema,
                        )
                        continue

                    if not isinstance(tool_name, str):
                        logger.warning(
                            "skipping_tool_invalid_name",
                            tool_name=tool_name,
                            tool_name_type=type(tool_name).__name__,
                        )
                        continue

                    # Determine category from tool name patterns
                    category = self._determine_category(tool_name, tool_schema)

                    # Create dynamic tool wrapper
                    dynamic_tool = MCPTool(
                        mcp_client=self.mcp_client,
                        tool_name=tool_name,
                        tool_description=tool_description,
                        tool_parameters=tool_parameters,
                        category=category,
                    )

                    # Register in tool registry
                    self.tool_registry.register(dynamic_tool)

                    logger.debug(
                        "registered_mcp_tool",
                        tool=tool_name,
                        category=category,
                    )

                    registered_count += 1

                except ValueError as e:
                    logger.warning(
                        "failed_to_create_mcp_tool",
                        error=str(e),
                        tool_name=tool_name,
                    )
                    continue
                except Exception as e:
                    logger.error(
                        "unexpected_error_loading_tool",
                        error=str(e),
                        tool_schema=tool_schema,
                    )
                    continue

            logger.info(
                "loading_mcp_tools_completed",
                registered_count=registered_count,
                total_tools=len(tools_list),
            )

            return registered_count

        except Exception as e:
            logger.error(
                "failed_to_load_mcp_tools",
                error=str(e),
            )
            raise

    def _determine_category(self, tool_name: str, tool_schema: dict[str, Any]) -> str:
        """
        Determine tool category based on name patterns and metadata.

        Args:
            tool_name: Name of the tool from MCP server
            tool_schema: Full tool schema from MCP server

        Returns:
            Category string for organizing tools
        """
        # Check for explicit category in schema
        if "category" in tool_schema:
            return str(tool_schema["category"])

        # Infer from tool name patterns
        name_lower = tool_name.lower()

        if any(keyword in name_lower for keyword in ["search", "query", "find", "lookup"]):
            return "search"

        if any(keyword in name_lower for keyword in ["create", "write", "insert", "add"]):
            return "write"

        if any(keyword in name_lower for keyword in ["delete", "remove", "drop"]):
            return "delete"

        if any(keyword in name_lower for keyword in ["analyze", "calculate", "compute"]):
            return "analysis"

        # Default to mcp category
        return "mcp"
