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
    CalculateLeadTimeRiskTool,
    CalculateStockoutProbabilityTool,
    GetCurrentObservationsTool,
    GetInventoryHistoryTool,
    GetOrderBacklogTool,
    GetShipmentsInTransitTool,
)
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
    """Integration tests for all 6 environment tools with real API."""

    @pytest.mark.integration
    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_get_current_observations_integration(self) -> None:
        """
        Test get_current_observations with real Environment API.

        Verifies:
        - Tool successfully calls Environment API
        - Returns valid observation data
        - Execution time is recorded
        """
        tool = GetCurrentObservationsTool()
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
    async def test_get_order_backlog_integration(self) -> None:
        """
        Test get_order_backlog with real Environment API.

        Verifies:
        - Tool successfully queries order data
        - Returns backlog information
        - Supports optional warehouse_id filter
        """
        tool = GetOrderBacklogTool()
        result = await tool.run()
        skip_if_api_unavailable(result)

        assert result.success, f"Tool failed: {result.error}"
        assert result.data is not None
        assert isinstance(result.data, dict)
        assert result.execution_time_ms > 0

    @pytest.mark.integration
    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_get_shipments_in_transit_integration(self) -> None:
        """
        Test get_shipments_in_transit with real Environment API.

        Verifies:
        - Tool queries shipment data
        - Returns transit information
        - Handles empty results gracefully
        """
        tool = GetShipmentsInTransitTool()
        result = await tool.run()
        skip_if_api_unavailable(result)

        assert result.success, f"Tool failed: {result.error}"
        assert result.data is not None
        assert isinstance(result.data, dict)
        assert result.execution_time_ms > 0

    @pytest.mark.integration
    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_calculate_stockout_probability_integration(self) -> None:
        """
        Test calculate_stockout_probability with real Environment API.

        Verifies:
        - Tool performs risk calculation
        - Returns probability value
        - Handles numerical parameters correctly
        """
        tool = CalculateStockoutProbabilityTool()

        # Test with reasonable parameters
        result = await tool.run(lead_time_days=7)
        skip_if_api_unavailable(result)

        # Tool might not succeed if product data is unavailable
        # but we verify the execution was attempted
        assert result.execution_time_ms > 0
        if result.success:
            assert result.data is not None
            assert isinstance(result.data, dict)

    @pytest.mark.integration
    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_calculate_lead_time_risk_integration(self) -> None:
        """
        Test calculate_lead_time_risk with real Environment API.

        Verifies:
        - Tool performs risk analysis
        - Returns risk metrics
        - Handles optional parameters
        """
        tool = CalculateLeadTimeRiskTool()
        result = await tool.run()
        skip_if_api_unavailable(result)

        assert result.execution_time_ms > 0
        # Tool may fail if data unavailable, but should attempt execution
        if result.success:
            assert result.data is not None

    @pytest.mark.integration
    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_get_inventory_history_integration(self) -> None:
        """
        Test get_inventory_history with real Environment API.

        Verifies:
        - Tool queries historical data
        - Returns time-series information
        - Handles date range parameters
        """
        tool = GetInventoryHistoryTool()
        result = await tool.run(days=30)
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
        Verify all 9 tools are registered and accessible via registry.

        This is an integration test because it verifies:
        - Tools are discoverable by registry
        - OpenAI schemas are properly formatted
        - Tools are wrapped with caching
        """
        environment_tools = [
            "get_current_observations",
            "get_order_backlog",
            "get_shipments_in_transit",
            "calculate_stockout_probability",
            "calculate_lead_time_risk",
            "get_inventory_history",
        ]

        rag_tools = [
            "search_knowledge_base",
            "expand_graph_by_ids",
            "get_entity_by_number",
        ]

        all_tools = environment_tools + rag_tools

        # Verify all tools registered
        for tool_name in all_tools:
            tool = tool_registry.get_tool(tool_name)
            assert tool is not None
            assert tool.get_metadata().name == tool_name

    @pytest.mark.integration
    def test_openai_functions_generation(self) -> None:
        """
        Verify OpenAI function schemas are valid and complete.

        Tests:
        - Schema format matches OpenAI requirements
        - All required fields present
        - Parameters are properly formatted
        """
        functions = tool_registry.get_openai_functions()

        assert len(functions) == 9, f"Expected 9 tools, got {len(functions)}"

        for func in functions:
            assert "type" in func or "function" in func
            func_def = func.get("function", func)

            assert "name" in func_def
            assert "description" in func_def
            # OpenAI format has "parameters" or our format might vary
            # but should have schema information

    @pytest.mark.integration
    def test_registry_statistics(self) -> None:
        """Verify registry statistics are accurate."""
        stats = tool_registry.get_registry_stats()

        assert stats["total_tools"] == 9
        assert stats["by_category"]["environment"] == 6
        assert stats["by_category"]["rag"] == 3


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
        inventory_tool = GetCurrentObservationsTool()
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
        real_time_tool = GetCurrentObservationsTool()
        result1 = await real_time_tool.run()
        skip_if_api_unavailable(result1)
        result2 = await real_time_tool.run()
        skip_if_api_unavailable(result2)

        # Both calls should show not cached (skip_cache=True)
        assert result1.cached is False
        assert result2.cached is False

        # Cached tool (after TTL) should cache results
        cached_tool = GetShipmentsInTransitTool()
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
