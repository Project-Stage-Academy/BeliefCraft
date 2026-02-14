"""
Unit tests for environment tools.

Tests all 7 environment tools:
- GetCurrentObservationsTool
- GetOrderBacklogTool
- GetShipmentsInTransitTool
- CalculateStockoutProbabilityTool
- CalculateLeadTimeRiskTool
- GetInventoryHistoryTool
"""

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from app.tools.environment_tools import (
    CalculateLeadTimeRiskTool,
    CalculateStockoutProbabilityTool,
    GetCurrentObservationsTool,
    GetInventoryHistoryTool,
    GetOrderBacklogTool,
    GetShipmentsInTransitTool,
)


@pytest.fixture
def mock_env_client() -> AsyncMock:
    """Create mock EnvironmentAPIClient."""
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock()
    return client


class TestGetCurrentObservationsTool:
    """Tests for GetCurrentObservationsTool."""

    @pytest.mark.asyncio
    async def test_metadata(self) -> None:
        """Test tool metadata is correct."""
        tool = GetCurrentObservationsTool()
        metadata = tool.get_metadata()

        assert metadata.name == "get_current_observations"
        assert metadata.category == "environment"
        assert "observations" in metadata.description.lower()
        assert "product_id" in metadata.parameters["properties"]
        assert "location_id" in metadata.parameters["properties"]
        assert "warehouse_id" in metadata.parameters["properties"]
        assert metadata.parameters["required"] == []

    @pytest.mark.asyncio
    async def test_execute_success_no_filters(self, mock_env_client: AsyncMock) -> None:
        """Test successful execution without filters."""
        tool = GetCurrentObservationsTool()

        mock_response = {
            "observations": [
                {"product_id": "P1", "quantity": 100, "location_id": "L1"},
                {"product_id": "P2", "quantity": 50, "location_id": "L2"},
            ]
        }
        mock_env_client.get_current_observations.return_value = mock_response

        with patch(
            "app.tools.environment_tools.EnvironmentAPIClient", return_value=mock_env_client
        ):
            result = await tool.execute()

            assert result == mock_response
            mock_env_client.get_current_observations.assert_called_once_with(
                product_id=None, location_id=None, warehouse_id=None
            )

    @pytest.mark.asyncio
    async def test_execute_success_with_filters(self, mock_env_client: AsyncMock) -> None:
        """Test successful execution with filters."""
        tool = GetCurrentObservationsTool()

        mock_response = {"observations": [{"product_id": "P1", "quantity": 100}]}
        mock_env_client.get_current_observations.return_value = mock_response

        with patch(
            "app.tools.environment_tools.EnvironmentAPIClient", return_value=mock_env_client
        ):
            result = await tool.execute(product_id="P1", warehouse_id="WH1")

            assert result == mock_response
            mock_env_client.get_current_observations.assert_called_once_with(
                product_id="P1", location_id=None, warehouse_id="WH1"
            )

    @pytest.mark.asyncio
    async def test_to_openai_function(self) -> None:
        """Test conversion to OpenAI function schema."""
        tool = GetCurrentObservationsTool()
        schema = tool.to_openai_function()

        assert schema["type"] == "function"
        assert schema["function"]["name"] == "get_current_observations"
        assert "parameters" in schema["function"]


class TestGetOrderBacklogTool:
    """Tests for GetOrderBacklogTool."""

    @pytest.mark.asyncio
    async def test_metadata(self) -> None:
        """Test tool metadata is correct."""
        tool = GetOrderBacklogTool()
        metadata = tool.get_metadata()

        assert metadata.name == "get_order_backlog"
        assert metadata.category == "environment"
        assert "order" in metadata.description.lower()
        assert "status" in metadata.parameters["properties"]
        assert "priority" in metadata.parameters["properties"]
        assert metadata.parameters["required"] == []

    @pytest.mark.asyncio
    async def test_execute_success(self, mock_env_client: AsyncMock) -> None:
        """Test successful execution."""
        tool = GetOrderBacklogTool()

        mock_response = {
            "orders": [
                {"order_id": "O1", "status": "pending", "priority": "high"},
                {"order_id": "O2", "status": "processing", "priority": "medium"},
            ]
        }
        mock_env_client.get_order_backlog.return_value = mock_response

        with patch(
            "app.tools.environment_tools.EnvironmentAPIClient", return_value=mock_env_client
        ):
            result = await tool.execute(status="pending", priority="high")

            assert result == mock_response
            mock_env_client.get_order_backlog.assert_called_once_with(
                status="pending", priority="high"
            )

    @pytest.mark.asyncio
    async def test_execute_without_filters(self, mock_env_client: AsyncMock) -> None:
        """Test execution without filters."""
        tool = GetOrderBacklogTool()

        mock_response: dict[str, Any] = {"orders": []}
        mock_env_client.get_order_backlog.return_value = mock_response

        with patch(
            "app.tools.environment_tools.EnvironmentAPIClient", return_value=mock_env_client
        ):
            result = await tool.execute()

            assert result == mock_response
            mock_env_client.get_order_backlog.assert_called_once_with(status=None, priority=None)


class TestGetShipmentsInTransitTool:
    """Tests for GetShipmentsInTransitTool."""

    @pytest.mark.asyncio
    async def test_metadata(self) -> None:
        """Test tool metadata is correct."""
        tool = GetShipmentsInTransitTool()
        metadata = tool.get_metadata()

        assert metadata.name == "get_shipments_in_transit"
        assert metadata.category == "environment"
        assert "shipment" in metadata.description.lower()
        assert "warehouse_id" in metadata.parameters["properties"]
        assert metadata.parameters["required"] == []

    @pytest.mark.asyncio
    async def test_execute_success(self, mock_env_client: AsyncMock) -> None:
        """Test successful execution."""
        tool = GetShipmentsInTransitTool()

        mock_response = {
            "shipments": [
                {"shipment_id": "S1", "status": "in_transit", "destination": "WH1"},
                {"shipment_id": "S2", "status": "in_transit", "destination": "WH2"},
            ]
        }
        mock_env_client.get_shipments_in_transit.return_value = mock_response

        with patch(
            "app.tools.environment_tools.EnvironmentAPIClient", return_value=mock_env_client
        ):
            result = await tool.execute(warehouse_id="WH1")

            assert result == mock_response
            mock_env_client.get_shipments_in_transit.assert_called_once_with(warehouse_id="WH1")


class TestCalculateStockoutProbabilityTool:
    """Tests for CalculateStockoutProbabilityTool."""

    @pytest.mark.asyncio
    async def test_metadata(self) -> None:
        """Test tool metadata is correct."""
        tool = CalculateStockoutProbabilityTool()
        metadata = tool.get_metadata()

        assert metadata.name == "calculate_stockout_probability"
        assert metadata.category == "environment"
        assert "stockout" in metadata.description.lower()
        assert "product_id" in metadata.parameters["properties"]
        assert metadata.parameters["required"] == ["product_id"]

    @pytest.mark.asyncio
    async def test_execute_success(self, mock_env_client: AsyncMock) -> None:
        """Test successful execution."""
        tool = CalculateStockoutProbabilityTool()

        mock_response = {
            "product_id": "P1",
            "probability": 0.35,
            "risk_level": "medium",
            "recommendation": "Consider reordering",
        }
        mock_env_client.calculate_stockout_probability.return_value = mock_response

        with patch(
            "app.tools.environment_tools.EnvironmentAPIClient", return_value=mock_env_client
        ):
            result = await tool.execute(product_id="P1")

            assert result == mock_response
            mock_env_client.calculate_stockout_probability.assert_called_once_with(product_id="P1")

    @pytest.mark.asyncio
    async def test_execute_high_risk(self, mock_env_client: AsyncMock) -> None:
        """Test execution with high stockout risk."""
        tool = CalculateStockoutProbabilityTool()

        mock_response = {"product_id": "P2", "probability": 0.85, "risk_level": "high"}
        mock_env_client.calculate_stockout_probability.return_value = mock_response

        with patch(
            "app.tools.environment_tools.EnvironmentAPIClient", return_value=mock_env_client
        ):
            result = await tool.execute(product_id="P2")

            assert result["probability"] == 0.85
            assert result["risk_level"] == "high"


class TestCalculateLeadTimeRiskTool:
    """Tests for CalculateLeadTimeRiskTool."""

    @pytest.mark.asyncio
    async def test_metadata(self) -> None:
        """Test tool metadata is correct."""
        tool = CalculateLeadTimeRiskTool()
        metadata = tool.get_metadata()

        assert metadata.name == "calculate_lead_time_risk"
        assert metadata.category == "environment"
        assert "lead time" in metadata.description.lower()
        assert "supplier_id" in metadata.parameters["properties"]
        assert "route_id" in metadata.parameters["properties"]
        assert metadata.parameters["required"] == []

    @pytest.mark.asyncio
    async def test_execute_success_with_supplier(self, mock_env_client: AsyncMock) -> None:
        """Test successful execution with supplier filter."""
        tool = CalculateLeadTimeRiskTool()

        mock_response = {
            "supplier_id": "SUP1",
            "mean_lead_time_days": 14,
            "std_dev": 3.5,
            "cvar_95": 21,
            "reliability_score": 0.85,
        }
        mock_env_client.calculate_lead_time_risk.return_value = mock_response

        with patch(
            "app.tools.environment_tools.EnvironmentAPIClient", return_value=mock_env_client
        ):
            result = await tool.execute(supplier_id="SUP1")

            assert result == mock_response
            mock_env_client.calculate_lead_time_risk.assert_called_once_with(
                supplier_id="SUP1", route_id=None
            )

    @pytest.mark.asyncio
    async def test_execute_success_with_route(self, mock_env_client: AsyncMock) -> None:
        """Test successful execution with route filter."""
        tool = CalculateLeadTimeRiskTool()

        mock_response: dict[str, Any] = {
            "route_id": "R1",
            "mean_lead_time_days": 7,
            "risk_level": "low",
        }
        mock_env_client.calculate_lead_time_risk.return_value = mock_response

        with patch(
            "app.tools.environment_tools.EnvironmentAPIClient", return_value=mock_env_client
        ):
            result = await tool.execute(route_id="R1")

            assert result == mock_response
            mock_env_client.calculate_lead_time_risk.assert_called_once_with(
                supplier_id=None, route_id="R1"
            )


class TestGetInventoryHistoryTool:
    """Tests for GetInventoryHistoryTool."""

    @pytest.mark.asyncio
    async def test_metadata(self) -> None:
        """Test tool metadata is correct."""
        tool = GetInventoryHistoryTool()
        metadata = tool.get_metadata()

        assert metadata.name == "get_inventory_history"
        assert metadata.category == "environment"
        assert "historical" in metadata.description.lower()
        assert "product_id" in metadata.parameters["properties"]
        assert "days" in metadata.parameters["properties"]
        assert metadata.parameters["required"] == ["product_id"]

    @pytest.mark.asyncio
    async def test_execute_success_default_days(self, mock_env_client: AsyncMock) -> None:
        """Test successful execution with default days parameter."""
        tool = GetInventoryHistoryTool()

        mock_response: dict[str, Any] = {
            "product_id": "P1",
            "days": 30,
            "history": [
                {"date": "2024-01-01", "quantity": 100},
                {"date": "2024-01-02", "quantity": 95},
            ],
        }
        mock_env_client.get_inventory_history.return_value = mock_response

        with patch(
            "app.tools.environment_tools.EnvironmentAPIClient", return_value=mock_env_client
        ):
            result = await tool.execute(product_id="P1")

            assert result == mock_response
            mock_env_client.get_inventory_history.assert_called_once_with(product_id="P1", days=30)

    @pytest.mark.asyncio
    async def test_execute_success_custom_days(self, mock_env_client: AsyncMock) -> None:
        """Test successful execution with custom days parameter."""
        tool = GetInventoryHistoryTool()

        mock_response: dict[str, Any] = {"product_id": "P1", "days": 90, "history": []}
        mock_env_client.get_inventory_history.return_value = mock_response

        with patch(
            "app.tools.environment_tools.EnvironmentAPIClient", return_value=mock_env_client
        ):
            result = await tool.execute(product_id="P1", days=90)

            assert result == mock_response
            mock_env_client.get_inventory_history.assert_called_once_with(product_id="P1", days=90)


class TestToolIntegration:
    """Integration tests for all environment tools."""

    @pytest.mark.asyncio
    async def test_all_tools_have_correct_category(self) -> None:
        """Test that all tools have 'environment' category."""
        tools = [
            GetCurrentObservationsTool(),
            GetOrderBacklogTool(),
            GetShipmentsInTransitTool(),
            CalculateStockoutProbabilityTool(),
            CalculateLeadTimeRiskTool(),
            GetInventoryHistoryTool(),
        ]

        for tool in tools:
            assert tool.metadata.category == "environment"

    @pytest.mark.asyncio
    async def test_all_tools_have_openai_schemas(self) -> None:
        """Test that all tools can generate OpenAI function schemas."""
        tools = [
            GetCurrentObservationsTool(),
            GetOrderBacklogTool(),
            GetShipmentsInTransitTool(),
            CalculateStockoutProbabilityTool(),
            CalculateLeadTimeRiskTool(),
            GetInventoryHistoryTool(),
        ]

        for tool in tools:
            schema = tool.to_openai_function()
            assert schema["type"] == "function"
            assert "function" in schema
            assert "name" in schema["function"]
            assert "description" in schema["function"]
            assert "parameters" in schema["function"]

    @pytest.mark.asyncio
    async def test_tool_run_wrapper_success(self, mock_env_client: AsyncMock) -> None:
        """Test that BaseTool.run() wrapper works correctly."""
        tool = GetCurrentObservationsTool()

        mock_response: dict[str, Any] = {"observations": []}
        mock_env_client.get_current_observations.return_value = mock_response

        with patch(
            "app.tools.environment_tools.EnvironmentAPIClient", return_value=mock_env_client
        ):
            result = await tool.run(product_id="P1")

            assert result.success is True
            assert result.data == mock_response
            assert result.execution_time_ms > 0
            assert result.error is None

    @pytest.mark.asyncio
    async def test_tool_run_wrapper_error(self) -> None:
        """Test that BaseTool.run() handles errors correctly."""
        tool = GetCurrentObservationsTool()

        # Create a mock that raises exception when method is called
        async def mock_get_observations(*args: Any, **kwargs: Any) -> None:
            raise Exception("API Error")

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get_current_observations = mock_get_observations

        with patch("app.tools.environment_tools.EnvironmentAPIClient", return_value=mock_client):
            result = await tool.run()

            assert result.success is False
            assert result.data is None
            assert result.error is not None
            assert "API Error" in result.error
            assert result.execution_time_ms > 0
