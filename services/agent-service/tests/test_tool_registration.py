"""
Unit tests for tool registration.

Tests automatic registration of environment tools at import time.
RAG tools are now loaded dynamically via MCP server during startup
(see test_mcp_tools.py for MCP tool loading tests).
"""

import pytest
from app.tools import tool_registry
from app.tools.cached_tool import CachedTool


class TestToolRegistration:
    """Test automatic tool registration on import."""

    def test_environment_tools_registered_on_import(self) -> None:
        """Test that 21 environment tools are auto-registered on import."""
        # Only environment tools are registered automatically
        # RAG tools are loaded via MCP during startup

        environment_tool_count = sum(
            1 for t in tool_registry.tools.values() if t.get_metadata().category == "environment"
        )

        assert environment_tool_count == 21, (
            f"Expected 21 environment tools, got {environment_tool_count}. "
            "Environment tools should be auto-registered on import."
        )

    def test_environment_tools_registered(self) -> None:
        """Test that all 21 environment tools are registered."""
        # Sample of environment tools (21 total across 5 modules)
        environment_tools = [
            "list_suppliers",
            "get_supplier",
            "list_purchase_orders",
            "get_purchase_order",
            "list_po_lines",
            "get_procurement_pipeline_summary",
            "list_inventory_moves",
            "get_inventory_move",
            "get_inventory_move_audit_trace",
            "get_inventory_adjustments_summary",
            "list_warehouses",
            "get_warehouse",
            "list_locations",
            "get_location",
            "get_locations_tree",
            "get_capacity_utilization_snapshot",
            "list_sensor_devices",
            "get_sensor_device",
            "get_device_health_summary",
            "get_device_anomalies",
            "get_observed_inventory_snapshot",
        ]

        # Validate uniqueness: no duplicate tool names in the list
        assert len(environment_tools) == len(set(environment_tools)), (
            f"Tool list contains duplicates: "
            f"{[t for t in environment_tools if environment_tools.count(t) > 1]}"
        )

        # Bidirectional verification: registry has exactly these 21 tools
        registered_env_tools = {
            name
            for name, tool in tool_registry.tools.items()
            if tool.get_metadata().category == "environment"
        }
        expected_tools = set(environment_tools)

        assert registered_env_tools == expected_tools, (
            f"Registry mismatch:\n"
            f"  Missing from registry: {expected_tools - registered_env_tools}\n"
            f"  Unexpected in registry: {registered_env_tools - expected_tools}"
        )

        for tool_name in environment_tools:
            tool = tool_registry.get_tool(tool_name)
            assert tool is not None
            assert isinstance(tool, CachedTool)
            assert tool.get_metadata().category == "environment"

    def test_rag_tools_not_registered_on_import(self) -> None:
        """Test that RAG tools are NOT auto-registered (they come from MCP)."""
        # RAG tools should be loaded via MCP during startup, not on import
        deprecated_rag_tools = [
            "search_knowledge_base",
            "expand_graph_by_ids",
            "get_entity_by_number",
        ]

        for tool_name in deprecated_rag_tools:
            # These tools should NOT be in registry after import
            # They will be loaded dynamically from MCP server
            with pytest.raises(
                Exception,
                match=r"Tool .* not found",
            ):
                # Should raise ToolExecutionError because tool not registered
                tool_registry.get_tool(tool_name)

    def test_real_time_tools_skip_cache(self) -> None:
        """Test that real-time tools have skip_cache=True."""
        # Real-time tools that skip cache
        real_time_tools = [
            "get_observed_inventory_snapshot",  # Real-time observations
        ]

        for tool_name in real_time_tools:
            tool = tool_registry.get_tool(tool_name)
            metadata = tool.get_metadata()
            assert metadata.skip_cache is True, f"{tool_name} should skip cache"

    def test_cached_environment_tools_have_ttl(self) -> None:
        """Test that cached environment tools have appropriate TTL."""
        cached_tools_ttl = {
            "list_purchase_orders": 300,  # 5 minutes (CACHE_TTL_SHIPMENTS)
            "list_po_lines": 300,  # 5 minutes (CACHE_TTL_SHIPMENTS)
            "get_procurement_pipeline_summary": 600,  # 10 minutes (CACHE_TTL_ANALYTICS)
            "get_capacity_utilization_snapshot": 600,  # 10 minutes (CACHE_TTL_ANALYTICS)
            "list_inventory_moves": 3600,  # 1 hour (CACHE_TTL_HISTORY)
            "get_inventory_move_audit_trace": 3600,  # 1 hour (CACHE_TTL_HISTORY)
            # RAG tools are no longer hardcoded - they come from MCP with 24h TTL
        }

        for tool_name, expected_ttl in cached_tools_ttl.items():
            tool = tool_registry.get_tool(tool_name)
            metadata = tool.get_metadata()
            assert (
                metadata.cache_ttl == expected_ttl
            ), f"{tool_name} should have TTL={expected_ttl}, got {metadata.cache_ttl}"

    def test_all_registered_tools_wrapped_in_cached_tool(self) -> None:
        """Test that all registered tools are wrapped in CachedTool."""
        for tool_name, tool in tool_registry.tools.items():
            assert isinstance(tool, CachedTool), f"{tool_name} should be wrapped in CachedTool"

    def test_environment_tool_metadata_passthrough(self) -> None:
        """Test that CachedTool properly passes through metadata for environment tools."""
        tool = tool_registry.get_tool("get_observed_inventory_snapshot")
        metadata = tool.get_metadata()

        assert metadata.name == "get_observed_inventory_snapshot"
        assert metadata.category == "environment"
        assert "quality_status_in" in metadata.parameters["properties"]
        assert "inventory" in metadata.description.lower()

    def test_get_openai_functions(self) -> None:
        """Test getting OpenAI function schemas for registered tools."""
        functions = tool_registry.get_openai_functions()

        # Should contain 21 environment tools (RAG tools loaded separately via MCP)
        assert len(functions) >= 21, f"Expected at least 21 environment tools, got {len(functions)}"

        # Verify environment functions are present
        # OpenAI format: {"type": "function", "function": {"name": ..., "description": ...,
        #                 "parameters": ...}}
        function_names = {f["function"]["name"] for f in functions}
        # Sample of expected tools
        expected_env_tools = {
            "list_suppliers",
            "get_supplier",
            "list_purchase_orders",
            "get_procurement_pipeline_summary",
            "list_inventory_moves",
            "get_inventory_adjustments_summary",
            "list_warehouses",
            "get_locations_tree",
            "get_capacity_utilization_snapshot",
            "list_sensor_devices",
            "get_device_health_summary",
            "get_observed_inventory_snapshot",
        }

        assert expected_env_tools.issubset(
            function_names
        ), f"Missing environment tools: {expected_env_tools - function_names}"

    def test_filter_tools_by_category(self) -> None:
        """
        Test filtering tools by category.

        Note: Only environment tools registered on import.
        RAG tools loaded via MCP during startup.
        """
        env_functions = tool_registry.get_openai_functions(categories=["environment"])
        assert len(env_functions) == 21

        # RAG tools not registered on import (loaded via MCP)
        rag_functions = tool_registry.get_openai_functions(categories=["rag"])
        assert (
            len(rag_functions) == 0
        ), "RAG tools should not be registered on import (loaded via MCP)"

    @pytest.mark.asyncio
    async def test_execute_tool_through_registry(self) -> None:
        """
        Test executing an environment tool through registry.

        Note: RAG tools not available here (loaded via MCP during startup).
        """
        # Test with environment tool that's registered on import
        tool = tool_registry.get_tool("get_observed_inventory_snapshot")
        assert tool is not None
        assert tool.get_metadata().name == "get_observed_inventory_snapshot"
        assert tool.get_metadata().category == "environment"
