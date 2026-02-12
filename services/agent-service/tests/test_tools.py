"""
Unit tests for tool system (BaseTool, ToolRegistry).

Tests cover:
- Tool metadata definition
- Tool execution with timing
- Error handling and recovery
- Registry operations
- OpenAI function schema generation
"""

import pytest
from typing import Any

from app.tools.base import BaseTool, ToolMetadata, ToolResult
from app.tools.registry import ToolRegistry
from app.core.exceptions import ToolExecutionError


# Mock tools for testing


class MockSuccessTool(BaseTool):
    """Tool that always succeeds."""
    
    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="mock_success",
            description="A tool that always succeeds",
            parameters={
                "type": "object",
                "properties": {
                    "value": {"type": "string", "description": "Input value"}
                },
                "required": ["value"]
            },
            category="utility"
        )
    
    async def execute(self, value: str) -> dict[str, Any]:
        return {"result": f"processed_{value}"}


class MockErrorTool(BaseTool):
    """Tool that always raises an error."""
    
    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="mock_error",
            description="A tool that always fails",
            parameters={
                "type": "object",
                "properties": {},
                "required": []
            },
            category="utility"
        )
    
    async def execute(self) -> dict[str, Any]:
        raise ValueError("Intentional error for testing")


class MockSlowTool(BaseTool):
    """Tool that simulates slow execution."""
    
    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="mock_slow",
            description="A slow tool",
            parameters={
                "type": "object",
                "properties": {},
                "required": []
            },
            category="utility"
        )
    
    async def execute(self) -> dict[str, Any]:
        import asyncio
        await asyncio.sleep(0.1)  # 100ms
        return {"completed": True}


class MockEnvironmentTool(BaseTool):
    """Tool in environment category."""
    
    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="mock_env",
            description="Environment tool",
            parameters={"type": "object", "properties": {}, "required": []},
            category="environment"
        )
    
    async def execute(self) -> dict[str, Any]:
        return {"warehouse": "WH1"}


class MockRAGTool(BaseTool):
    """Tool in RAG category."""
    
    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="mock_rag",
            description="RAG tool",
            parameters={"type": "object", "properties": {}, "required": []},
            category="rag"
        )
    
    async def execute(self) -> dict[str, Any]:
        return {"documents": ["doc1", "doc2"]}


# Tests


class TestToolMetadata:
    """Tests for ToolMetadata model."""
    
    def test_metadata_creation(self):
        """Test creating valid metadata."""
        metadata = ToolMetadata(
            name="test_tool",
            description="Test description",
            parameters={"type": "object", "properties": {}},
            category="utility"
        )
        
        assert metadata.name == "test_tool"
        assert metadata.description == "Test description"
        assert metadata.category == "utility"
    
    def test_metadata_immutable(self):
        """Test that metadata is frozen (immutable)."""
        metadata = ToolMetadata(
            name="test",
            description="test",
            parameters={},
            category="utility"
        )
        
        with pytest.raises(Exception):  # Pydantic ValidationError
            metadata.name = "modified"


class TestToolResult:
    """Tests for ToolResult model."""
    
    def test_success_result(self):
        """Test creating successful result."""
        result = ToolResult(
            success=True,
            data={"key": "value"},
            execution_time_ms=123.45
        )
        
        assert result.success is True
        assert result.data == {"key": "value"}
        assert result.error is None
        assert result.execution_time_ms == 123.45
        assert result.cached is False
    
    def test_error_result(self):
        """Test creating error result."""
        result = ToolResult(
            success=False,
            error="Something went wrong",
            execution_time_ms=50.0
        )
        
        assert result.success is False
        assert result.data is None
        assert result.error == "Something went wrong"
    
    def test_cached_result(self):
        """Test cached result flag."""
        result = ToolResult(
            success=True,
            data="cached_data",
            execution_time_ms=0.5,
            cached=True
        )
        
        assert result.cached is True


class TestBaseTool:
    """Tests for BaseTool abstract class."""
    
    @pytest.mark.asyncio
    async def test_tool_success_execution(self):
        """Test successful tool execution."""
        tool = MockSuccessTool()
        result = await tool.run(value="test123")
        
        assert result.success is True
        assert result.data == {"result": "processed_test123"}
        assert result.error is None
        assert result.execution_time_ms > 0
    
    @pytest.mark.asyncio
    async def test_tool_error_handling(self):
        """Test tool error is caught and returned."""
        tool = MockErrorTool()
        result = await tool.run()
        
        assert result.success is False
        assert result.data is None
        assert "ValueError" in result.error
        assert "Intentional error" in result.error
        assert result.execution_time_ms > 0
    
    @pytest.mark.asyncio
    async def test_tool_timing_accuracy(self):
        """Test execution timing is accurate."""
        tool = MockSlowTool()
        result = await tool.run()
        
        # Should be around 100ms (allow 20ms tolerance)
        assert result.execution_time_ms >= 90
        assert result.execution_time_ms < 150
    
    def test_tool_metadata_access(self):
        """Test metadata is accessible."""
        tool = MockSuccessTool()
        
        assert tool.metadata.name == "mock_success"
        assert tool.metadata.category == "utility"
        assert "value" in tool.metadata.parameters["properties"]
    
    def test_to_openai_function(self):
        """Test OpenAI function schema conversion."""
        tool = MockSuccessTool()
        schema = tool.to_openai_function()
        
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "mock_success"
        assert schema["function"]["description"] == "A tool that always succeeds"
        assert "parameters" in schema["function"]
        assert schema["function"]["parameters"]["type"] == "object"


class TestToolRegistry:
    """Tests for ToolRegistry."""
    
    def test_registry_initialization(self):
        """Test registry starts empty."""
        registry = ToolRegistry()
        assert len(registry.list_tools()) == 0
    
    def test_register_tool(self):
        """Test registering a tool."""
        registry = ToolRegistry()
        tool = MockSuccessTool()
        
        registry.register(tool)
        
        assert len(registry.list_tools()) == 1
        assert registry.get_tool("mock_success") == tool
    
    def test_register_duplicate_raises_error(self):
        """Test registering duplicate tool name raises error."""
        registry = ToolRegistry()
        tool1 = MockSuccessTool()
        tool2 = MockSuccessTool()
        
        registry.register(tool1)
        
        with pytest.raises(ValueError, match="already registered"):
            registry.register(tool2)
    
    def test_get_nonexistent_tool_raises_error(self):
        """Test getting non-existent tool raises error."""
        registry = ToolRegistry()
        
        with pytest.raises(ToolExecutionError, match="not found"):
            registry.get_tool("nonexistent")
    
    def test_list_tools_no_filter(self):
        """Test listing all tools."""
        registry = ToolRegistry()
        registry.register(MockSuccessTool())
        registry.register(MockErrorTool())
        registry.register(MockEnvironmentTool())
        
        tools = registry.list_tools()
        assert len(tools) == 3
    
    def test_list_tools_by_category(self):
        """Test filtering tools by category."""
        registry = ToolRegistry()
        registry.register(MockSuccessTool())
        registry.register(MockEnvironmentTool())
        registry.register(MockRAGTool())
        
        utility_tools = registry.list_tools(category="utility")
        assert len(utility_tools) == 1
        assert utility_tools[0].metadata.name == "mock_success"
        
        env_tools = registry.list_tools(category="environment")
        assert len(env_tools) == 1
        
        rag_tools = registry.list_tools(category="rag")
        assert len(rag_tools) == 1
    
    def test_get_tool_names(self):
        """Test getting list of tool names."""
        registry = ToolRegistry()
        registry.register(MockSuccessTool())
        registry.register(MockErrorTool())
        
        names = registry.get_tool_names()
        assert "mock_success" in names
        assert "mock_error" in names
        assert len(names) == 2
    
    def test_get_tool_names_by_category(self):
        """Test getting tool names filtered by category."""
        registry = ToolRegistry()
        registry.register(MockSuccessTool())
        registry.register(MockEnvironmentTool())
        
        names = registry.get_tool_names(category="environment")
        assert names == ["mock_env"]
    
    def test_get_openai_functions_all(self):
        """Test getting OpenAI schemas for all tools."""
        registry = ToolRegistry()
        registry.register(MockSuccessTool())
        registry.register(MockErrorTool())
        
        functions = registry.get_openai_functions()
        
        assert len(functions) == 2
        assert all(f["type"] == "function" for f in functions)
        assert any(f["function"]["name"] == "mock_success" for f in functions)
    
    def test_get_openai_functions_filtered(self):
        """Test getting OpenAI schemas filtered by category."""
        registry = ToolRegistry()
        registry.register(MockSuccessTool())
        registry.register(MockEnvironmentTool())
        registry.register(MockRAGTool())
        
        functions = registry.get_openai_functions(
            categories=["environment", "rag"]
        )
        
        assert len(functions) == 2
        names = [f["function"]["name"] for f in functions]
        assert "mock_env" in names
        assert "mock_rag" in names
        assert "mock_success" not in names
    
    @pytest.mark.asyncio
    async def test_execute_tool_success(self):
        """Test executing tool through registry."""
        registry = ToolRegistry()
        registry.register(MockSuccessTool())
        
        result = await registry.execute_tool(
            "mock_success",
            {"value": "test"}
        )
        
        assert result.success is True
        assert result.data == {"result": "processed_test"}
    
    @pytest.mark.asyncio
    async def test_execute_tool_error(self):
        """Test executing tool that raises error."""
        registry = ToolRegistry()
        registry.register(MockErrorTool())
        
        result = await registry.execute_tool("mock_error", {})
        
        assert result.success is False
        assert "ValueError" in result.error
    
    @pytest.mark.asyncio
    async def test_execute_nonexistent_tool(self):
        """Test executing non-existent tool raises error."""
        registry = ToolRegistry()
        
        with pytest.raises(ToolExecutionError):
            await registry.execute_tool("nonexistent", {})
    
    def test_get_registry_stats(self):
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
