"""
RAG MCP Client for agent-service.

This module provides a client for connecting to the RAG service's MCP server
to dynamically discover and execute RAG tools.

The client wraps FastMCP's HTTP client and implements our MCPClientProtocol
for type-safe integration with MCPToolLoader.

Example:
    ```python
    from app.clients.rag_mcp_client import RAGMCPClient

    async with RAGMCPClient("http://localhost:8001") as client:
        tools = await client.list_tools()
        result = await client.call_tool("search_knowledge_base", {"query": "POMDP"})
    ```
"""

from typing import Any

from app.core.constants import MCP_REQUEST_TIMEOUT
from app.tools.mcp_tool import MCPClientProtocol
from common.http_client import TracedHttpClient
from common.logging import get_logger
from fastmcp.client import Client, StreamableHttpTransport

logger = get_logger(__name__)


class RAGMCPClient:
    """
    HTTP client for RAG service MCP server.

    This client wraps FastMCP's Client to provide:
    - Automatic connection management
    - Tool discovery (list_tools)
    - Tool execution (call_tool)
    - Implements MCPClientProtocol for type safety

    Attributes:
        base_url: RAG service base URL (e.g., "http://localhost:8001")
        mcp_path: MCP endpoint path (default: "/mcp")
        http_client: Underlying HTTP client for requests
        mcp_client: FastMCP client instance
    """

    def __init__(
        self,
        base_url: str,
        mcp_path: str = "/mcp",
        timeout: int = MCP_REQUEST_TIMEOUT,
    ) -> None:
        """
        Initialize RAG MCP client.

        Args:
            base_url: RAG service base URL (e.g., "http://localhost:8001")
            mcp_path: MCP endpoint path (default: "/mcp")
            timeout: HTTP request timeout in seconds

        Raises:
            ValueError: If base_url is empty or whitespace-only
        """
        if not base_url or not base_url.strip():
            raise ValueError("base_url cannot be empty or whitespace-only")

        self.base_url = base_url.strip().rstrip("/")
        self.mcp_path = mcp_path
        self.mcp_url = f"{self.base_url}{self.mcp_path}"
        self.timeout = timeout

        self.http_client: TracedHttpClient | None = None
        self.mcp_client: Client[Any, Any] | None = None  # type: ignore[type-arg]

        logger.debug(
            "rag_mcp_client_initialized",
            mcp_url=self.mcp_url,
            timeout=timeout,
        )

    async def __aenter__(self) -> "RAGMCPClient":
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.close()

    async def connect(self) -> None:
        """
        Establish connection to MCP server.

        Creates HTTP client and FastMCP client instances.
        If FastMCP fails during session startup, any partially initialized
        resources are cleaned up before the original error is re-raised.
        """
        # Create traced HTTP client for observability
        http_client = TracedHttpClient(
            base_url=self.base_url,
            timeout=self.timeout,
        )
        await http_client.__aenter__()
        self.http_client = http_client

        # FastMCP passes args/kwargs to the factory, but we intentionally ignore them
        # because our httpx.AsyncClient is pre-configured in __aenter__() with all
        # necessary settings (timeout, base_url, tracing). The factory just returns
        # the existing client rather than creating a new one.
        transport = StreamableHttpTransport(
            self.mcp_url,
            httpx_client_factory=lambda *args, **kwargs: http_client.get_httpx_client(),
        )

        # Create FastMCP client
        mcp_client = Client(transport)
        self.mcp_client = mcp_client

        try:
            await mcp_client.__aenter__()  # type: ignore[no-untyped-call]
        except Exception:
            await self.close()
            raise

        logger.info(
            "rag_mcp_client_connected",
            mcp_url=self.mcp_url,
        )

    async def close(self) -> None:
        """Close connection to MCP server using best-effort cleanup."""
        mcp_client = self.mcp_client
        http_client = self.http_client

        self.mcp_client = None
        self.http_client = None

        if mcp_client:
            try:
                await mcp_client.__aexit__(None, None, None)  # type: ignore[no-untyped-call]
            except Exception as e:
                logger.warning(
                    "rag_mcp_client_disconnect_failed",
                    error=str(e),
                    error_type=type(e).__name__,
                    mcp_url=self.mcp_url,
                )

        if http_client:
            try:
                await http_client.__aexit__(None, None, None)
            except Exception as e:
                logger.warning(
                    "rag_mcp_http_client_disconnect_failed",
                    error=str(e),
                    error_type=type(e).__name__,
                    base_url=self.base_url,
                )

        logger.debug("rag_mcp_client_closed")

    async def list_tools(self) -> list[dict[str, Any]]:
        """
        List all available tools from MCP server.

        Returns:
            List of tool schemas with name, description, and parameters

        Raises:
            RuntimeError: If client is not connected
            Exception: If MCP server communication fails
        """
        if not self.mcp_client:
            raise RuntimeError(
                "MCP client not connected. Call connect() first or use async context manager."
            )

        logger.debug("listing_mcp_tools")

        tools = await self.mcp_client.list_tools()

        # Convert FastMCP Tool objects to dictionaries
        tools_list = [
            {
                "name": tool.name,
                "description": tool.description or "",
                "parameters": tool.inputSchema if hasattr(tool, "inputSchema") else {},
            }
            for tool in tools
        ]

        logger.info(
            "mcp_tools_listed",
            tool_count=len(tools_list),
            tool_names=[t["name"] for t in tools_list],
        )

        return tools_list

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        """
        Execute a tool on the MCP server.

        Args:
            name: Tool name to execute
            arguments: Tool input arguments

        Returns:
            Tool execution result

        Raises:
            RuntimeError: If client is not connected
            Exception: If tool execution fails
        """
        if not self.mcp_client:
            raise RuntimeError(
                "MCP client not connected. Call connect() first or use async context manager."
            )

        logger.debug(
            "calling_mcp_tool",
            tool_name=name,
            arguments=arguments,
        )

        result = await self.mcp_client.call_tool(name, arguments)

        logger.info(
            "mcp_tool_called",
            tool_name=name,
            result_type=type(result).__name__,
        )

        return result


# Type check: RAGMCPClient implements MCPClientProtocol
if False:  # Only for static type checking, never executed at runtime
    from typing import cast

    _client: MCPClientProtocol = cast(RAGMCPClient, None)
