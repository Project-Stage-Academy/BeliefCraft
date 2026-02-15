"""
Unit tests for tool system (BaseTool, ToolRegistry).
"""

from typing import Any
from unittest.mock import AsyncMock

import pytest
from app.core.exceptions import ToolExecutionError
from app.tools.base import APIClientTool, BaseTool, ToolMetadata
from app.tools.registry import ToolRegistry


class MockSuccessTool(BaseTool):
    """Tool that always succeeds."""

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="mock_success",
            description="A tool that always succeeds",
            parameters={
                "type": "object",
                "properties": {"value": {"type": "string", "description": "Input value"}},
                "required": ["value"],
            },
            category="utility",
        )

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        """Виправлено: використання **kwargs для сумісності з BaseTool."""
        value = kwargs.get("value", "")
        return {"result": f"processed_{value}"}


class MockErrorTool(BaseTool):
    """Tool that always raises an error."""

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="mock_error",
            description="A tool that always fails",
            parameters={"type": "object", "properties": {}, "required": []},
            category="utility",
        )

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        """Виправлено: сигнатура **kwargs."""
        raise ValueError("Mock error")


class MockEnvironmentTool(BaseTool):
    """Mock environment tool."""

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="mock_env",
            description="Env tool",
            category="environment",
        )

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        """Виправлено: сигнатура **kwargs."""
        return {"status": "ok"}


class MockRAGTool(BaseTool):
    """Mock RAG tool."""

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="mock_rag",
            description="RAG tool",
            category="rag",
        )

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        """Виправлено: сигнатура **kwargs."""
        return {"found": True}


class TestBaseTool:
    """Tests for BaseTool functionality."""

    @pytest.mark.asyncio
    async def test_tool_run_success(self) -> None:
        """Test successful tool execution with timing."""
        tool = MockSuccessTool()
        result = await tool.run(value="test")

        assert result.success is True
        assert result.data == {"result": "processed_test"}
        assert result.execution_time_ms > 0
        assert result.error is None

    @pytest.mark.asyncio
    async def test_tool_run_error(self) -> None:
        """Test tool execution with error handling."""
        tool = MockErrorTool()
        result = await tool.run()

        assert result.success is False
        assert result.data is None
        assert "ValueError" in result.error if result.error else False
        assert result.execution_time_ms > 0

    def test_to_openai_function(self) -> None:
        """Test conversion to OpenAI function schema."""
        tool = MockSuccessTool()
        schema = tool.to_openai_function()

        assert schema["type"] == "function"
        assert schema["function"]["name"] == "mock_success"
        assert "value" in schema["function"]["parameters"]["properties"]


class TestToolRegistry:
    """Tests for ToolRegistry functionality."""

    def test_register_tool(self) -> None:
        """Test registering tools."""
        registry = ToolRegistry()
        registry.register(MockSuccessTool())

        assert "mock_success" in registry.tools
        assert isinstance(registry.get_tool("mock_success"), MockSuccessTool)

    def test_get_tool_by_category(self) -> None:
        """Test filtering tools by category."""
        registry = ToolRegistry()
        registry.register(MockSuccessTool())
        registry.register(MockEnvironmentTool())

        env_tools = registry.get_tools_by_category("environment")
        assert len(env_tools) == 1
        assert env_tools[0].metadata.name == "mock_env"

    def test_get_openai_functions(self) -> None:
        """Test getting all tools as OpenAI functions."""
        registry = ToolRegistry()
        registry.register(MockSuccessTool())
        registry.register(MockRAGTool())

        functions = registry.get_openai_functions()
        assert len(functions) == 2
        assert any(f["function"]["name"] == "mock_success" for f in functions)

    @pytest.mark.asyncio
    async def test_execute_tool_success(self) -> None:
        """Test executing tool through registry."""
        registry = ToolRegistry()
        registry.register(MockSuccessTool())

        result = await registry.execute_tool("mock_success", {"value": "test"})

        assert result.success is True
        assert result.data == {"result": "processed_test"}

    @pytest.mark.asyncio
    async def test_execute_tool_error(self) -> None:
        """Test executing tool that raises error."""
        registry = ToolRegistry()
        registry.register(MockErrorTool())

        result = await registry.execute_tool("mock_error", {})

        assert result.success is False
        assert result.error is not None
        assert "ValueError" in result.error

    @pytest.mark.asyncio
    async def test_execute_nonexistent_tool(self) -> None:
        """Test executing non-existent tool raises error."""
        registry = ToolRegistry()

        with pytest.raises(ToolExecutionError):
            await registry.execute_tool("nonexistent", {})

    def test_get_registry_stats(self) -> None:
        """Test getting registry statistics."""
        registry = ToolRegistry()
        registry.register(MockSuccessTool())
        registry.register(MockErrorTool())
        registry.register(MockEnvironmentTool())
        registry.register(MockRAGTool())

        stats = registry.get_registry_stats()

        assert stats["total_tools"] == 4
        assert stats["by_category"]["utility"] == 2
        assert stats["by_category"]["environment"] == 1
        assert stats["by_category"]["rag"] == 1


class TestValidateRequiredParams:
    """Tests for _validate_required_params method."""

    def test_validate_all_params_present(self) -> None:
        """Test validation passes when all required params present."""
        tool = MockSuccessTool()
        # Should not raise
        tool._validate_required_params(["value"], {"value": "test"})

    def test_validate_missing_single_param(self) -> None:
        """Test validation fails when single required param missing."""
        tool = MockSuccessTool()
        with pytest.raises(ValueError, match="Missing required parameter.*value"):
            tool._validate_required_params(["value"], {})

    def test_validate_missing_multiple_params(self) -> None:
        """Test validation fails when multiple required params missing."""
        tool = MockSuccessTool()
        with pytest.raises(ValueError, match="Missing required parameter.*param1.*param2"):
            tool._validate_required_params(["param1", "param2"], {})

    def test_validate_partial_params(self) -> None:
        """Test validation fails when only some params present."""
        tool = MockSuccessTool()
        with pytest.raises(ValueError, match="Missing required parameter.*param2"):
            tool._validate_required_params(["param1", "param2"], {"param1": "value"})

    def test_validate_extra_params_allowed(self) -> None:
        """Test validation passes with extra parameters."""
        tool = MockSuccessTool()
        # Should not raise - extra params are ok
        tool._validate_required_params(["value"], {"value": "test", "extra": "ignored"})


class MockAPIClient:
    """Mock API client for testing APIClientTool."""

    def __init__(self) -> None:
        self.fetch_data = AsyncMock(return_value={"result": "default"})

    async def __aenter__(self) -> "MockAPIClient":
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        pass


class MockAPIClientTool(APIClientTool):
    """Mock tool using APIClientTool base class."""

    def __init__(self, client: MockAPIClient | None = None) -> None:
        self._client = client
        super().__init__()

    def get_client(self) -> MockAPIClient:
        """Get API client instance."""
        return self._client or MockAPIClient()

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="mock_api_tool",
            description="Test API tool",
            parameters={
                "type": "object",
                "properties": {"param": {"type": "string"}},
                "required": ["param"],
            },
            category="test",
        )

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        self._validate_required_params(["param"], kwargs)
        async with self.get_client() as client:
            result: dict[str, Any] = await client.fetch_data(kwargs["param"])
            return result


class TestAPIClientTool:
    """Tests for APIClientTool base class."""

    @pytest.mark.asyncio
    async def test_api_client_tool_with_injected_client(self) -> None:
        """Test APIClientTool works with injected client."""
        mock_client = MockAPIClient()
        mock_client.fetch_data = AsyncMock(return_value={"result": "test_value"})

        tool = MockAPIClientTool(client=mock_client)
        result = await tool.execute(param="test_value")

        assert result == {"result": "test_value"}
        mock_client.fetch_data.assert_called_once_with("test_value")

    @pytest.mark.asyncio
    async def test_api_client_tool_creates_client_if_none(self) -> None:
        """Test APIClientTool creates client if none injected."""
        tool = MockAPIClientTool()
        # Should create client internally - just check tool works
        assert tool.get_client() is not None

    @pytest.mark.asyncio
    async def test_api_client_tool_validates_params(self) -> None:
        """Test APIClientTool validates required parameters."""
        tool = MockAPIClientTool()

        with pytest.raises(ValueError, match="Missing required parameter.*param"):
            await tool.execute()  # Missing required param

    def test_get_client_not_implemented(self) -> None:
        """Test that APIClientTool.get_client() must be overridden."""

        class IncompleteAPITool(APIClientTool):
            def get_metadata(self) -> ToolMetadata:
                return ToolMetadata(name="incomplete", description="test", category="test")

            async def execute(self, **kwargs: Any) -> dict[str, Any]:
                return {}

            # Missing get_client() override

        tool = IncompleteAPITool()
        with pytest.raises(NotImplementedError):
            tool.get_client()
