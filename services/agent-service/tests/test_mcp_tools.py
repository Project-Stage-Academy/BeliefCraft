"""
Unit tests for MCP tool wrapper and loader.
"""

from unittest.mock import AsyncMock, Mock

import pytest
from app.tools.mcp_loader import MCPToolLoader
from app.tools.mcp_tool import MCPClientProtocol, MCPTool
from app.tools.registry import ToolRegistry


class TestMCPTool:
    """Tests for MCPTool wrapper."""

    @pytest.fixture
    def mock_mcp_client(self) -> Mock:
        """Create mock MCP client."""
        client = AsyncMock(spec=MCPClientProtocol)
        return client

    @pytest.fixture
    def tool_registry(self) -> ToolRegistry:
        """Create tool registry for testing."""
        return ToolRegistry()

    def test_mcp_tool_initialization_valid(self, mock_mcp_client: Mock) -> None:
        """Test MCPTool initialization with valid parameters."""
        tool = MCPTool(
            mcp_client=mock_mcp_client,
            tool_name="search_documents",
            tool_description="Search for documents in knowledge base",
            tool_parameters={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
            category="search",
        )

        assert tool._tool_name == "search_documents"
        assert tool._tool_description == "Search for documents in knowledge base"
        assert tool._category == "search"
        assert tool.mcp_client is mock_mcp_client

    def test_mcp_tool_initialization_invalid_name(self, mock_mcp_client: Mock) -> None:
        """Test MCPTool initialization with invalid tool_name."""
        with pytest.raises(ValueError, match="tool_name must be a non-empty string"):
            MCPTool(
                mcp_client=mock_mcp_client,
                tool_name="",
                tool_description="Test tool",
                tool_parameters={},
            )

    def test_mcp_tool_initialization_invalid_description(self, mock_mcp_client: Mock) -> None:
        """Test MCPTool initialization with invalid tool_description."""
        with pytest.raises(ValueError, match="tool_description must be a non-empty string"):
            MCPTool(
                mcp_client=mock_mcp_client,
                tool_name="test_tool",
                tool_description="",
                tool_parameters={},
            )

    def test_mcp_tool_initialization_invalid_parameters(self, mock_mcp_client: Mock) -> None:
        """Test MCPTool initialization with invalid tool_parameters."""
        with pytest.raises(ValueError, match="tool_parameters must be a dictionary"):
            MCPTool(
                mcp_client=mock_mcp_client,
                tool_name="test_tool",
                tool_description="Test tool",
                tool_parameters="invalid",  # type: ignore[arg-type]
            )

    def test_mcp_tool_get_metadata(self, mock_mcp_client: Mock) -> None:
        """Test MCPTool.get_metadata() returns correct ToolMetadata."""
        tool = MCPTool(
            mcp_client=mock_mcp_client,
            tool_name="test_tool",
            tool_description="Test description",
            tool_parameters={"type": "object", "properties": {}},
            category="mcp",
        )

        metadata = tool.get_metadata()

        assert metadata.name == "test_tool"
        assert metadata.description == "Test description"
        assert metadata.category == "mcp"
        assert metadata.parameters == {"type": "object", "properties": {}}

    @pytest.mark.asyncio
    async def test_mcp_tool_execute_success(self, mock_mcp_client: Mock) -> None:
        """Test successful tool execution through MCP client."""
        mock_mcp_client.call_tool.return_value = {"result": "success", "data": [1, 2, 3]}

        tool = MCPTool(
            mcp_client=mock_mcp_client,
            tool_name="test_tool",
            tool_description="Test tool",
            tool_parameters={},
        )

        result = await tool.execute(query="test query")

        assert result == {"result": "success", "data": [1, 2, 3]}
        mock_mcp_client.call_tool.assert_called_once_with(
            name="test_tool",
            arguments={"query": "test query"},
        )

    @pytest.mark.asyncio
    async def test_mcp_tool_execute_error(self, mock_mcp_client: Mock) -> None:
        """Test tool execution when MCP client raises exception."""
        mock_mcp_client.call_tool.side_effect = Exception("MCP server error")

        tool = MCPTool(
            mcp_client=mock_mcp_client,
            tool_name="test_tool",
            tool_description="Test tool",
            tool_parameters={},
        )

        with pytest.raises(Exception, match="MCP server error"):
            await tool.execute(query="test")

    @pytest.mark.asyncio
    async def test_mcp_tool_execute_cast_to_dict(self, mock_mcp_client: Mock) -> None:
        """Test that result is cast to dict[str, Any]."""
        # Return a non-dict that should be cast
        mock_mcp_client.call_tool.return_value = {"wrapped": "result"}

        tool = MCPTool(
            mcp_client=mock_mcp_client,
            tool_name="test_tool",
            tool_description="Test tool",
            tool_parameters={},
        )

        result = await tool.execute()

        assert isinstance(result, dict)
        assert result == {"wrapped": "result"}


class TestMCPToolLoader:
    """Tests for MCPToolLoader."""

    @pytest.fixture
    def mock_mcp_client(self) -> Mock:
        """Create mock MCP client."""
        client = AsyncMock(spec=MCPClientProtocol)
        return client

    @pytest.fixture
    def tool_registry(self) -> ToolRegistry:
        """Create fresh tool registry."""
        return ToolRegistry()

    def test_mcp_tool_loader_initialization_valid(
        self, mock_mcp_client: Mock, tool_registry: ToolRegistry
    ) -> None:
        """Test MCPToolLoader initialization with valid parameters."""
        loader = MCPToolLoader(
            mcp_client=mock_mcp_client,
            tool_registry=tool_registry,
        )

        assert loader.mcp_client is mock_mcp_client
        assert loader.tool_registry is tool_registry

    def test_mcp_tool_loader_initialization_invalid_client(
        self, tool_registry: ToolRegistry
    ) -> None:
        """Test MCPToolLoader initialization with None client."""
        with pytest.raises(ValueError, match="mcp_client cannot be None"):
            MCPToolLoader(
                mcp_client=None,  # type: ignore[arg-type]
                tool_registry=tool_registry,
            )

    def test_mcp_tool_loader_initialization_invalid_registry(self, mock_mcp_client: Mock) -> None:
        """Test MCPToolLoader initialization with None registry."""
        with pytest.raises(ValueError, match="tool_registry cannot be None"):
            MCPToolLoader(
                mcp_client=mock_mcp_client,
                tool_registry=None,  # type: ignore[arg-type]
            )

    @pytest.mark.asyncio
    async def test_mcp_tool_loader_load_tools_success(
        self, mock_mcp_client: Mock, tool_registry: ToolRegistry
    ) -> None:
        """Test successful tool loading from MCP server."""
        mock_mcp_client.list_tools.return_value = [
            {
                "name": "search_knowledge_base",
                "description": "Search knowledge base",
                "inputSchema": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
            },
            {
                "name": "retrieve_document",
                "description": "Retrieve document by ID",
                "inputSchema": {
                    "type": "object",
                    "properties": {"doc_id": {"type": "string"}},
                    "required": ["doc_id"],
                },
            },
        ]

        loader = MCPToolLoader(
            mcp_client=mock_mcp_client,
            tool_registry=tool_registry,
        )

        registered_count = await loader.load_tools()

        assert registered_count == 2
        mock_mcp_client.list_tools.assert_called_once()

    @pytest.mark.asyncio
    async def test_mcp_tool_loader_load_tools_empty(
        self, mock_mcp_client: Mock, tool_registry: ToolRegistry
    ) -> None:
        """Test tool loading when no tools available."""
        mock_mcp_client.list_tools.return_value = []

        loader = MCPToolLoader(
            mcp_client=mock_mcp_client,
            tool_registry=tool_registry,
        )

        registered_count = await loader.load_tools()

        assert registered_count == 0

    @pytest.mark.asyncio
    async def test_mcp_tool_loader_load_tools_invalid_response(
        self, mock_mcp_client: Mock, tool_registry: ToolRegistry
    ) -> None:
        """Test tool loading when server returns invalid response."""
        mock_mcp_client.list_tools.return_value = "not_a_list"

        loader = MCPToolLoader(
            mcp_client=mock_mcp_client,
            tool_registry=tool_registry,
        )

        registered_count = await loader.load_tools()

        assert registered_count == 0

    @pytest.mark.asyncio
    async def test_mcp_tool_loader_skip_invalid_tools(
        self, mock_mcp_client: Mock, tool_registry: ToolRegistry
    ) -> None:
        """Test that invalid tools are skipped without stopping loader."""
        mock_mcp_client.list_tools.return_value = [
            {
                "name": "valid_tool",
                "description": "Valid tool",
                "inputSchema": {},
            },
            {
                # Missing name
                "description": "Invalid tool 1",
                "inputSchema": {},
            },
            {
                "name": 123,  # Invalid name type
                "description": "Invalid tool 2",
                "inputSchema": {},
            },
            {
                "name": "another_valid_tool",
                "description": "Another valid tool",
                "inputSchema": {},
            },
        ]

        loader = MCPToolLoader(
            mcp_client=mock_mcp_client,
            tool_registry=tool_registry,
        )

        registered_count = await loader.load_tools()

        # Should register only valid tools (2 out of 4)
        assert registered_count == 2

    @pytest.mark.asyncio
    async def test_mcp_tool_loader_error_handling(
        self, mock_mcp_client: Mock, tool_registry: ToolRegistry
    ) -> None:
        """Test error handling when list_tools fails."""
        mock_mcp_client.list_tools.side_effect = Exception("Connection failed")

        loader = MCPToolLoader(
            mcp_client=mock_mcp_client,
            tool_registry=tool_registry,
        )

        with pytest.raises(Exception, match="Connection failed"):
            await loader.load_tools()

    def test_mcp_tool_loader_determine_category_search(
        self, mock_mcp_client: Mock, tool_registry: ToolRegistry
    ) -> None:
        """Test category determination for search tools."""
        loader = MCPToolLoader(
            mcp_client=mock_mcp_client,
            tool_registry=tool_registry,
        )

        assert loader._determine_category("search_documents", {}) == "search"
        assert loader._determine_category("query_database", {}) == "search"
        assert loader._determine_category("find_by_id", {}) == "search"

    def test_mcp_tool_loader_determine_category_write(
        self, mock_mcp_client: Mock, tool_registry: ToolRegistry
    ) -> None:
        """Test category determination for write tools."""
        loader = MCPToolLoader(
            mcp_client=mock_mcp_client,
            tool_registry=tool_registry,
        )

        assert loader._determine_category("create_document", {}) == "write"
        assert loader._determine_category("insert_record", {}) == "write"
        assert loader._determine_category("add_item", {}) == "write"

    def test_mcp_tool_loader_determine_category_delete(
        self, mock_mcp_client: Mock, tool_registry: ToolRegistry
    ) -> None:
        """Test category determination for delete tools."""
        loader = MCPToolLoader(
            mcp_client=mock_mcp_client,
            tool_registry=tool_registry,
        )

        assert loader._determine_category("delete_document", {}) == "delete"
        assert loader._determine_category("remove_item", {}) == "delete"

    def test_mcp_tool_loader_determine_category_analysis(
        self, mock_mcp_client: Mock, tool_registry: ToolRegistry
    ) -> None:
        """Test category determination for analysis tools."""
        loader = MCPToolLoader(
            mcp_client=mock_mcp_client,
            tool_registry=tool_registry,
        )

        assert loader._determine_category("analyze_data", {}) == "analysis"
        assert loader._determine_category("calculate_metrics", {}) == "analysis"

    def test_mcp_tool_loader_determine_category_explicit(
        self, mock_mcp_client: Mock, tool_registry: ToolRegistry
    ) -> None:
        """Test category determination with explicit category in schema."""
        loader = MCPToolLoader(
            mcp_client=mock_mcp_client,
            tool_registry=tool_registry,
        )

        category = loader._determine_category(
            "unknown_tool",
            {"category": "custom"},
        )

        assert category == "custom"

    def test_mcp_tool_loader_determine_category_default(
        self, mock_mcp_client: Mock, tool_registry: ToolRegistry
    ) -> None:
        """Test category determination defaults to 'mcp'."""
        loader = MCPToolLoader(
            mcp_client=mock_mcp_client,
            tool_registry=tool_registry,
        )

        assert loader._determine_category("random_tool_name", {}) == "mcp"
