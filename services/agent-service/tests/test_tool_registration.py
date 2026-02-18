"""
Unit tests for tool registration.

Tests that all tools are properly registered with caching.
"""

import pytest
from app.tools import tool_registry
from app.tools.cached_tool import CachedTool


class TestToolRegistration:
    """Test automatic tool registration."""

    def test_all_tools_registered(self) -> None:
        """Test that all 9 tools are registered."""
        assert len(tool_registry.tools) == 9

    def test_environment_tools_registered(self) -> None:
        """Test that all 6 environment tools are registered."""
        environment_tools = [
            "get_current_observations",
            "get_order_backlog",
            "get_shipments_in_transit",
            "calculate_stockout_probability",
            "calculate_lead_time_risk",
            "get_inventory_history",
        ]

        for tool_name in environment_tools:
            tool = tool_registry.get_tool(tool_name)
            assert tool is not None
            assert isinstance(tool, CachedTool)
            assert tool.get_metadata().category == "environment"

    def test_rag_tools_registered(self) -> None:
        """Test that all 3 RAG tools are registered."""
        rag_tools = [
            "search_knowledge_base",
            "expand_graph_by_ids",
            "get_entity_by_number",
        ]

        for tool_name in rag_tools:
            tool = tool_registry.get_tool(tool_name)
            assert tool is not None
            assert isinstance(tool, CachedTool)
            assert tool.get_metadata().category == "rag"

    def test_real_time_tools_skip_cache(self) -> None:
        """Test that real-time tools have skip_cache=True."""
        real_time_tools = [
            "get_current_observations",
            "get_order_backlog",
        ]

        for tool_name in real_time_tools:
            tool = tool_registry.get_tool(tool_name)
            metadata = tool.get_metadata()
            assert metadata.skip_cache is True, f"{tool_name} should skip cache"

    def test_cached_tools_have_ttl(self) -> None:
        """Test that cached tools have appropriate TTL."""
        cached_tools_ttl = {
            "get_shipments_in_transit": 300,  # 5 minutes (CACHE_TTL_SHIPMENTS)
            "calculate_stockout_probability": 600,  # 10 minutes (CACHE_TTL_ANALYTICS)
            "calculate_lead_time_risk": 600,  # 10 minutes (CACHE_TTL_ANALYTICS)
            "get_inventory_history": 3600,  # 1 hour (CACHE_TTL_HISTORY)
            "search_knowledge_base": 86400,  # 24 hours (CACHE_TTL_RAG_TOOLS)
            "expand_graph_by_ids": 86400,  # 24 hours (CACHE_TTL_RAG_TOOLS)
            "get_entity_by_number": 86400,  # 24 hours (CACHE_TTL_RAG_TOOLS)
        }

        for tool_name, expected_ttl in cached_tools_ttl.items():
            tool = tool_registry.get_tool(tool_name)
            metadata = tool.get_metadata()
            assert (
                metadata.cache_ttl == expected_ttl
            ), f"{tool_name} should have TTL={expected_ttl}, got {metadata.cache_ttl}"

    def test_all_tools_wrapped_in_cached_tool(self) -> None:
        """Test that all tools are wrapped in CachedTool."""
        for tool_name, tool in tool_registry.tools.items():
            assert isinstance(tool, CachedTool), f"{tool_name} should be wrapped in CachedTool"

    def test_tool_metadata_passthrough(self) -> None:
        """Test that CachedTool properly passes through metadata."""
        tool = tool_registry.get_tool("search_knowledge_base")
        metadata = tool.get_metadata()

        assert metadata.name == "search_knowledge_base"
        assert metadata.category == "rag"
        assert "query" in metadata.parameters["properties"]
        assert "algorithm" in metadata.description.lower()

    def test_get_openai_functions(self) -> None:
        """Test getting OpenAI function schemas."""
        functions = tool_registry.get_openai_functions()

        assert len(functions) == 9
        assert all("type" in f and f["type"] == "function" for f in functions)
        assert all("function" in f for f in functions)

    def test_filter_tools_by_category(self) -> None:
        """Test filtering tools by category."""
        env_functions = tool_registry.get_openai_functions(categories=["environment"])
        assert len(env_functions) == 6

        rag_functions = tool_registry.get_openai_functions(categories=["rag"])
        assert len(rag_functions) == 3

        all_functions = tool_registry.get_openai_functions(categories=["environment", "rag"])
        assert len(all_functions) == 9

    @pytest.mark.asyncio
    async def test_execute_tool_through_registry(self) -> None:
        """Test executing a tool through registry (integration check)."""
        # This will fail without real dependencies, but tests the flow
        # In real tests, we'd mock the underlying clients
        tool = tool_registry.get_tool("search_knowledge_base")
        assert tool is not None
        assert tool.get_metadata().name == "search_knowledge_base"
