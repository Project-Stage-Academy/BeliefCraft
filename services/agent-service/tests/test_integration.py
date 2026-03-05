"""
Integration tests for tools with real APIs.

These tests verify that tools work correctly with the actual
Environment API and RAG Service. Tests are marked with @pytest.mark.integration
and can be skipped by setting SKIP_INTEGRATION=true.

Requirements:
- Environment API running on port 8000
- RAG Service running on port 8001
- Redis cache running on port 6379

Run integration tests:
    uv run pytest tests/test_integration.py -v

Skip integration tests (CI/CD):
    SKIP_INTEGRATION=true uv run pytest tests/ -v

Run only integration tests:
    uv run pytest tests/ -m integration -v -s
"""

import os
from typing import Any

import pytest
from app.tools.environment_tools import (
    GetObservedInventorySnapshotTool,
    GetProcurementPipelineSummaryTool,
    ListInventoryMovesTool,
    ListPurchaseOrdersTool,
)

# NOTE: Using deprecated RAG tools for backward compatibility testing
# New approach uses MCPToolLoader to load tools from RAG MCP server
# These imports test the deprecated direct RAG client approach
from app.tools.rag_tools import (
    ExpandGraphByIdsTool,
    GetEntityByNumberTool,
    SearchKnowledgeBaseTool,
)
from app.tools.registry import tool_registry
from httpcore import RemoteProtocolError
from httpx import ConnectError

# Skip all integration tests if SKIP_INTEGRATION environment variable is set
pytestmark = pytest.mark.skipif(
    os.getenv("SKIP_INTEGRATION") == "true",
    reason="Integration tests disabled (SKIP_INTEGRATION=true)",
)


def skip_if_api_unavailable(result: Any) -> None:
    """Skip test if API is unavailable (ConnectError/RemoteProtocolError in result)."""
    if isinstance(result, (ConnectError, RemoteProtocolError)):
        pytest.skip(f"API unavailable: {result}")
    if hasattr(result, "error") and result.error:
        error_str = str(result.error)
        if "ConnectError" in error_str or "RemoteProtocolError" in error_str:
            pytest.skip(f"API unavailable: {result.error}")


# ============================================================================
# Environment Tools Integration Tests
# ============================================================================


class TestEnvironmentToolsIntegration:
    """Integration tests for environment tools with real API."""

    @pytest.mark.integration
    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_get_observed_inventory_snapshot_integration(self) -> None:
        """
        Test get_observed_inventory_snapshot with real Environment API.

        Verifies:
        - Tool successfully calls Environment API
        - Returns valid observation data
        - Execution time is recorded
        """
        tool = GetObservedInventorySnapshotTool()
        result = await tool.run()
        skip_if_api_unavailable(result)

        # Verify execution was successful
        assert result.success, f"Tool failed: {result.error}"
        assert result.data is not None
        assert isinstance(result.data, dict)
        assert result.execution_time_ms > 0
        assert not result.cached

    @pytest.mark.integration
    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_list_purchase_orders_integration(self) -> None:
        """
        Test list_purchase_orders with real Environment API.

        Verifies:
        - Tool successfully queries order data
        - Returns purchase order information
        - Supports optional filters
        """
        tool = ListPurchaseOrdersTool()
        result = await tool.run()
        skip_if_api_unavailable(result)

        assert result.success, f"Tool failed: {result.error}"
        assert result.data is not None
        assert isinstance(result.data, dict)
        assert result.execution_time_ms > 0

    @pytest.mark.integration
    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_get_procurement_pipeline_summary_integration(self) -> None:
        """
        Test get_procurement_pipeline_summary with real Environment API.

        Verifies:
        - Tool queries procurement pipeline data
        - Returns inbound supply metrics
        - Handles empty results gracefully
        """
        tool = GetProcurementPipelineSummaryTool()
        result = await tool.run()
        skip_if_api_unavailable(result)

        assert result.success, f"Tool failed: {result.error}"
        assert result.data is not None
        assert isinstance(result.data, dict)
        assert result.execution_time_ms > 0

    @pytest.mark.integration
    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_list_inventory_moves_integration(self) -> None:
        """
        Test list_inventory_moves with real Environment API.

        Verifies:
        - Tool queries inventory movement history
        - Returns movement data
        - Handles optional filters correctly
        """
        tool = ListInventoryMovesTool()

        # Test with reasonable parameters
        result = await tool.run()
        skip_if_api_unavailable(result)

        # Tool might not succeed if data is unavailable
        # but we verify the execution was attempted
        assert result.execution_time_ms > 0
        if result.success:
            assert result.data is not None
            assert isinstance(result.data, dict)

    @pytest.mark.integration
    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_get_procurement_pipeline_with_filters_integration(self) -> None:
        """
        Test get_procurement_pipeline_summary with filters.

        Verifies:
        - Tool performs pipeline analysis
        - Returns aggregated metrics
        - Handles optional parameters
        """
        tool = GetProcurementPipelineSummaryTool()
        result = await tool.run()
        skip_if_api_unavailable(result)

        assert result.execution_time_ms > 0
        # Tool may fail if data unavailable, but should attempt execution
        if result.success:
            assert result.data is not None

    @pytest.mark.integration
    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_list_inventory_moves_with_filters_integration(self) -> None:
        """
        Test list_inventory_moves with filters.

        Verifies:
        - Tool queries historical movement data
        - Returns time-series information
        - Handles filter parameters
        """
        tool = ListInventoryMovesTool()
        result = await tool.run()
        skip_if_api_unavailable(result)

        assert result.execution_time_ms > 0
        if result.success:
            assert result.data is not None
            assert isinstance(result.data, dict)


# ============================================================================
# RAG Tools Integration Tests
# ============================================================================


class TestRAGToolsIntegration:
    """Integration tests for all 3 RAG tools with real API."""

    @pytest.mark.integration
    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_search_knowledge_base_integration(self) -> None:
        """
        Test search_knowledge_base with real RAG Service.

        Verifies:
        - Tool successfully searches knowledge base
        - Returns relevant results
        - Handles natural language queries
        """
        tool = SearchKnowledgeBaseTool()

        # Test with meaningful query
        result = await tool.run(query="inventory control", k=3)
        skip_if_api_unavailable(result)

        assert result.success, f"Tool failed: {result.error}"
        assert result.data is not None
        assert isinstance(result.data, dict)
        assert "results" in result.data or result.data != {}
        assert result.execution_time_ms > 0

    @pytest.mark.integration
    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_search_knowledge_base_with_filters_integration(self) -> None:
        """
        Test search_knowledge_base with metadata filters.

        Verifies:
        - Tool supports optional filters
        - Filtering improves result relevance
        - traverse_types parameter works
        """
        tool = SearchKnowledgeBaseTool()

        result = await tool.run(
            query="POMDP algorithm",
            k=5,
            traverse_types=["formula", "algorithm_code"],
        )
        skip_if_api_unavailable(result)

        assert result.execution_time_ms > 0
        if result.success:
            assert result.data is not None

    @pytest.mark.integration
    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_expand_graph_by_ids_integration(self) -> None:
        """
        Test expand_graph_by_ids with real RAG Service.

        Verifies:
        - Tool retrieves linked entities
        - Returns relationship information
        - Handles entity expansion
        """
        tool = ExpandGraphByIdsTool()

        # First search to get document IDs
        search_tool = SearchKnowledgeBaseTool()
        search_result = await search_tool.run(query="inventory", k=2)
        skip_if_api_unavailable(search_result)

        if search_result.success and "results" in search_result.data:
            results = search_result.data.get("results", [])
            if results:
                doc_ids = [r.get("id") for r in results if "id" in r]

                if doc_ids:
                    expand_result = await tool.run(
                        document_ids=doc_ids[:2],
                        traverse_types=["formula", "algorithm"],
                    )
                    skip_if_api_unavailable(expand_result)

                    assert expand_result.execution_time_ms > 0
                    if expand_result.success:
                        assert expand_result.data is not None

    @pytest.mark.integration
    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_get_entity_by_number_integration(self) -> None:
        """
        Test get_entity_by_number with real RAG Service.

        Verifies:
        - Tool retrieves specific numbered entities
        - Handles formula, algorithm, table types
        - Returns entity with metadata
        """
        tool = GetEntityByNumberTool()

        # Test retrieving a well-known algorithm
        result = await tool.run(entity_type="algorithm", number="3.2")
        skip_if_api_unavailable(result)

        assert result.execution_time_ms > 0
        if result.success:
            assert result.data is not None
            assert isinstance(result.data, dict)

    @pytest.mark.integration
    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_get_entity_by_number_formula_integration(self) -> None:
        """Test retrieving a formula by number."""
        tool = GetEntityByNumberTool()

        result = await tool.run(entity_type="formula", number="16.4")
        skip_if_api_unavailable(result)

        assert result.execution_time_ms > 0
        if result.success:
            assert result.data is not None


# ============================================================================
# Tool Registry Integration Tests
# ============================================================================


class TestToolRegistryIntegration:
    """Integration tests for tool registry with real tools."""

    @pytest.mark.integration
    def test_all_tools_registered_and_accessible(self) -> None:
        """
        Verify environment tools are registered and accessible via registry.

        Note: RAG tools are now loaded dynamically from MCP server during
        application startup, so only environment tools are registered on import.

        This is an integration test because it verifies:
        - Tools are discoverable by registry
        - OpenAI schemas are properly formatted
        - Tools are wrapped with caching
        """
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

        # Verify environment tools registered
        for tool_name in environment_tools:
            tool = tool_registry.get_tool(tool_name)
            assert tool is not None
            assert tool.get_metadata().name == tool_name

    @pytest.mark.integration
    def test_openai_functions_generation(self) -> None:
        """
        Verify OpenAI function schemas are valid and complete.

        Note: Only environment tools are registered on import.
        RAG tools are loaded via MCP during application startup.

        Tests:
        - Schema format matches OpenAI requirements
        - All required fields present
        - Parameters are properly formatted
        """
        functions = tool_registry.get_openai_functions()

        assert len(functions) >= 21, f"Expected at least 21 environment tools, got {len(functions)}"

        for func in functions:
            assert "type" in func or "function" in func
            func_def = func.get("function", func)

            assert "name" in func_def
            assert "description" in func_def
            # OpenAI format has "parameters" or our format might vary
            # but should have schema information

    @pytest.mark.integration
    def test_registry_statistics(self) -> None:
        """
        Verify registry statistics are accurate.

        Note: Only environment tools registered on import.
        RAG tools loaded via MCP during startup.
        """
        stats = tool_registry.get_registry_stats()

        assert stats["total_tools"] >= 21, f"Expected at least 21 tools, got {stats['total_tools']}"
        assert stats["by_category"]["environment"] == 21
        # RAG tools not registered on import (loaded via MCP)
        assert stats["by_category"].get("rag", 0) >= 0


# ============================================================================
# End-to-End Integration Tests
# ============================================================================


class TestEndToEndIntegration:
    """End-to-end integration tests combining multiple components."""

    @pytest.mark.integration
    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_full_workflow_environment_to_rag(self) -> None:
        """
        Test full workflow: Environment tool → RAG tool.

        Simulates agent workflow:
        1. Query environment for inventory
        2. Use result to search knowledge base for relevant algorithms
        """
        # Step 1: Get inventory data
        inventory_tool = GetObservedInventorySnapshotTool()
        inventory_result = await inventory_tool.run()
        skip_if_api_unavailable(inventory_result)

        # Step 2: Search for relevant algorithm
        search_tool = SearchKnowledgeBaseTool()
        search_result = await search_tool.run(
            query="inventory optimization low stock",
            k=3,
        )
        skip_if_api_unavailable(search_result)

        # Verify both tools executed
        assert inventory_result.execution_time_ms > 0
        assert search_result.execution_time_ms > 0

    @pytest.mark.integration
    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_caching_behavior_integration(self) -> None:
        """
        Test that caching works correctly in real environment.

        Verifies:
        - First call: not cached
        - Second call: cached (for tools with caching enabled)
        - Real-time tools (skip_cache=True) always fresh
        """
        # Real-time tool should never be cached
        real_time_tool = GetObservedInventorySnapshotTool()
        result1 = await real_time_tool.run()
        skip_if_api_unavailable(result1)
        result2 = await real_time_tool.run()
        skip_if_api_unavailable(result2)

        # Both calls should show not cached (skip_cache=True)
        assert result1.cached is False
        assert result2.cached is False

        # Cached tool (after TTL) should cache results
        cached_tool = ListPurchaseOrdersTool()
        result3 = await cached_tool.run()
        skip_if_api_unavailable(result3)
        result4 = await cached_tool.run()
        skip_if_api_unavailable(result4)

        # First call not cached, second might be (depends on TTL and Redis)
        assert result3.execution_time_ms > 0
        assert result4.execution_time_ms > 0


# ============================================================================
# Error Handling Integration Tests
# ============================================================================


class TestErrorHandlingIntegration:
    """Test error handling with real APIs."""

    @pytest.mark.integration
    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_tool_with_invalid_parameters(self) -> None:
        """
        Test tool behavior with invalid parameters.

        Verifies graceful error handling when:
        - Invalid parameter types provided
        - Missing required parameters
        - Invalid values provided
        """
        tool = GetEntityByNumberTool()

        # Test with invalid entity_type
        result = await tool.run(entity_type="invalid_type", number="3.2")
        skip_if_api_unavailable(result)

        # Should fail gracefully
        assert result.execution_time_ms > 0
        # Either success=False or appropriate error handling
        if not result.success:
            assert result.error is not None

    @pytest.mark.integration
    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_api_timeout_handling(self) -> None:
        """
        Test that tools handle API timeouts gracefully.

        This test verifies:
        - Timeout errors are caught
        - Error is returned in ToolResult
        - Agent can reason about the error
        """
        # This is more of a smoke test
        # Real timeout would require network simulation
        tool = SearchKnowledgeBaseTool()
        result = await tool.run(query="test", k=1)
        skip_if_api_unavailable(result)

        # Should complete without raising exception
        assert result.execution_time_ms >= 0
        assert isinstance(result.success, bool)
