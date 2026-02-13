"""
Unit tests for tool system (BaseTool, ToolRegistry).
"""

from typing import Any

import pytest
from app.core.exceptions import ToolExecutionError
from app.tools.base import BaseTool, ToolMetadata
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
