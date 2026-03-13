"""
Unit tests for environment tools.

Tests all 21 environment tools organized by module:
- PROCUREMENT MODULE (6 tools)
- INVENTORY AUDIT MODULE (4 tools)
- TOPOLOGY MODULE (6 tools)
- DEVICE MONITORING MODULE (4 tools)
- OBSERVED INVENTORY MODULE (1 tool)
"""

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

# Import all environment tools (21 total across 5 modules)
from app.tools.environment_tools import (
    GetCapacityUtilizationSnapshotTool,
    GetDeviceAnomaliesTool,
    GetDeviceHealthSummaryTool,
    GetInventoryAdjustmentsSummaryTool,
    GetInventoryMoveAuditTraceTool,
    GetInventoryMoveTool,
    GetLocationsTreeTool,
    GetLocationTool,
    GetObservedInventorySnapshotTool,
    GetProcurementPipelineSummaryTool,
    GetPurchaseOrderTool,
    GetSensorDeviceTool,
    GetSupplierTool,
    GetWarehouseTool,
    ListInventoryMovesTool,
    ListLocationsTool,
    ListPOLinesTool,
    ListPurchaseOrdersTool,
    ListSensorDevicesTool,
    ListSuppliersTool,
    ListWarehousesTool,
)


@pytest.fixture
def mock_env_client() -> AsyncMock:
    """Create mock EnvironmentAPIClient."""
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock()
    return client


# ========================================
# PROCUREMENT MODULE TESTS (6 tools)
# ========================================


class TestListSuppliersTool:
    """Tests for ListSuppliersTool."""

    @pytest.mark.asyncio
    async def test_metadata(self) -> None:
        """Test tool metadata is correct."""
        tool = ListSuppliersTool()
        metadata = tool.get_metadata()

        assert metadata.name == "list_suppliers"
        assert metadata.category == "environment"
        assert "supplier" in metadata.description.lower()
        assert "region" in metadata.parameters["properties"]
        assert metadata.parameters["required"] == []

    @pytest.mark.asyncio
    async def test_execute_success(self, mock_env_client: AsyncMock) -> None:
        """Test successful execution."""
        tool = ListSuppliersTool()

        mock_response = {
            "suppliers": [
                {"id": "SUP1", "name": "Supplier A", "reliability_score": 0.95, "region": "US"},
                {"id": "SUP2", "name": "Supplier B", "reliability_score": 0.88, "region": "EU"},
            ]
        }
        mock_env_client.list_suppliers.return_value = mock_response

        with patch(
            "app.tools.environment_tools.EnvironmentAPIClient", return_value=mock_env_client
        ):
            result = await tool.execute(region="US", reliability_min=0.9)

            assert result == mock_response
            mock_env_client.list_suppliers.assert_called_once_with(
                region="US", reliability_min=0.9, name_like=None
            )


class TestListPurchaseOrdersTool:
    """Tests for ListPurchaseOrdersTool."""

    @pytest.mark.asyncio
    async def test_metadata(self) -> None:
        """Test tool metadata is correct."""
        tool = ListPurchaseOrdersTool()
        metadata = tool.get_metadata()

        assert metadata.name == "list_purchase_orders"
        assert metadata.category == "environment"
        assert "purchase order" in metadata.description.lower()
        assert "supplier_id" in metadata.parameters["properties"]

    @pytest.mark.asyncio
    async def test_execute_with_filters(self, mock_env_client: AsyncMock) -> None:
        """Test execution with filters."""
        tool = ListPurchaseOrdersTool()

        mock_response: dict[str, Any] = {
            "purchase_orders": [
                {"id": "PO1", "supplier_id": "SUP1", "status": "pending"},
            ]
        }
        mock_env_client.list_purchase_orders.return_value = mock_response

        with patch(
            "app.tools.environment_tools.EnvironmentAPIClient", return_value=mock_env_client
        ):
            result = await tool.execute(supplier_id="SUP1", status_in=["pending", "confirmed"])

            assert result == mock_response
            mock_env_client.list_purchase_orders.assert_called_once()


class TestGetProcurementPipelineSummaryTool:
    """Tests for GetProcurementPipelineSummaryTool."""

    @pytest.mark.asyncio
    async def test_metadata(self) -> None:
        """Test tool metadata is correct."""
        tool = GetProcurementPipelineSummaryTool()
        metadata = tool.get_metadata()

        assert metadata.name == "get_procurement_pipeline_summary"
        assert metadata.category == "environment"
        assert "pipeline" in metadata.description.lower()

    @pytest.mark.asyncio
    async def test_execute_success(self, mock_env_client: AsyncMock) -> None:
        """Test successful execution."""
        tool = GetProcurementPipelineSummaryTool()

        mock_response = {
            "open_po_count": 15,
            "total_qty_ordered": 1000,
            "total_qty_received": 650,
            "total_remaining": 350,
        }
        mock_env_client.get_procurement_pipeline_summary.return_value = mock_response

        with patch(
            "app.tools.environment_tools.EnvironmentAPIClient", return_value=mock_env_client
        ):
            result = await tool.execute(destination_warehouse_id="WH1")

            assert result == mock_response
            mock_env_client.get_procurement_pipeline_summary.assert_called_once()


# ========================================
# INVENTORY AUDIT MODULE TESTS (4 tools)
# ========================================


class TestListInventoryMovesTool:
    """Tests for ListInventoryMovesTool."""

    @pytest.mark.asyncio
    async def test_metadata(self) -> None:
        """Test tool metadata is correct."""
        tool = ListInventoryMovesTool()
        metadata = tool.get_metadata()

        assert metadata.name == "list_inventory_moves"
        assert metadata.category == "environment"
        assert "movement" in metadata.description.lower()
        assert "warehouse_id" in metadata.parameters["properties"]
        assert "product_id" in metadata.parameters["properties"]

    @pytest.mark.asyncio
    async def test_execute_success(self, mock_env_client: AsyncMock) -> None:
        """Test successful execution."""
        tool = ListInventoryMovesTool()

        mock_response = {
            "moves": [
                {"id": "M1", "product_id": "P1", "move_type": "transfer", "qty": 50},
                {"id": "M2", "product_id": "P2", "move_type": "adjustment", "qty": -10},
            ]
        }
        mock_env_client.list_inventory_moves.return_value = mock_response

        with patch(
            "app.tools.environment_tools.EnvironmentAPIClient", return_value=mock_env_client
        ):
            result = await tool.execute(warehouse_id="WH1", move_type="adjustment")

            assert result == mock_response
            mock_env_client.list_inventory_moves.assert_called_once()


class TestGetInventoryMoveAuditTraceTool:
    """Tests for GetInventoryMoveAuditTraceTool."""

    @pytest.mark.asyncio
    async def test_metadata(self) -> None:
        """Test tool metadata is correct."""
        tool = GetInventoryMoveAuditTraceTool()
        metadata = tool.get_metadata()

        assert metadata.name == "get_inventory_move_audit_trace"
        assert metadata.category == "environment"
        assert "audit" in metadata.description.lower()
        assert metadata.parameters["required"] == ["move_id"]

    @pytest.mark.asyncio
    async def test_execute_success(self, mock_env_client: AsyncMock) -> None:
        """Test successful execution."""
        tool = GetInventoryMoveAuditTraceTool()

        mock_response = {
            "move": {"id": "M1", "product_id": "P1"},
            "observations": [{"id": "O1", "related_move_id": "M1"}],
        }
        mock_env_client.get_inventory_move_audit_trace.return_value = mock_response

        with patch(
            "app.tools.environment_tools.EnvironmentAPIClient", return_value=mock_env_client
        ):
            result = await tool.execute(move_id="M1")

            assert result == mock_response
            mock_env_client.get_inventory_move_audit_trace.assert_called_once_with(move_id="M1")


class TestGetInventoryAdjustmentsSummaryTool:
    """Tests for GetInventoryAdjustmentsSummaryTool."""

    @pytest.mark.asyncio
    async def test_metadata(self) -> None:
        """Test tool metadata is correct."""
        tool = GetInventoryAdjustmentsSummaryTool()
        metadata = tool.get_metadata()

        assert metadata.name == "get_inventory_adjustments_summary"
        assert metadata.category == "environment"
        assert "adjustment" in metadata.description.lower()

    @pytest.mark.asyncio
    async def test_execute_success(self, mock_env_client: AsyncMock) -> None:
        """Test successful execution."""
        tool = GetInventoryAdjustmentsSummaryTool()

        mock_response = {
            "count": 25,
            "total_qty": -150,
            "breakdown": {"damaged": -80, "lost": -50, "found": 20},
        }
        mock_env_client.get_inventory_adjustments_summary.return_value = mock_response

        with patch(
            "app.tools.environment_tools.EnvironmentAPIClient", return_value=mock_env_client
        ):
            result = await tool.execute(warehouse_id="WH1", product_id="P1")

            assert result == mock_response


# ========================================
# TOPOLOGY MODULE TESTS (6 tools)
# ========================================


class TestListWarehousesTool:
    """Tests for ListWarehousesTool."""

    @pytest.mark.asyncio
    async def test_metadata(self) -> None:
        """Test tool metadata is correct."""
        tool = ListWarehousesTool()
        metadata = tool.get_metadata()

        assert metadata.name == "list_warehouses"
        assert metadata.category == "environment"
        assert "warehouse" in metadata.description.lower()

    @pytest.mark.asyncio
    async def test_execute_success(self, mock_env_client: AsyncMock) -> None:
        """Test successful execution."""
        tool = ListWarehousesTool()

        mock_response = {
            "warehouses": [
                {"id": "WH1", "name": "Main Warehouse", "region": "US", "tz": "America/New_York"},
                {"id": "WH2", "name": "EU Warehouse", "region": "EU", "tz": "Europe/Paris"},
            ]
        }
        mock_env_client.list_warehouses.return_value = mock_response

        with patch(
            "app.tools.environment_tools.EnvironmentAPIClient", return_value=mock_env_client
        ):
            result = await tool.execute(region="US")

            assert result == mock_response
            mock_env_client.list_warehouses.assert_called_once_with(region="US")


class TestListLocationsTool:
    """Tests for ListLocationsTool."""

    @pytest.mark.asyncio
    async def test_metadata(self) -> None:
        """Test tool metadata is correct."""
        tool = ListLocationsTool()
        metadata = tool.get_metadata()

        assert metadata.name == "list_locations"
        assert metadata.category == "environment"
        assert "location" in metadata.description.lower()
        assert metadata.parameters["required"] == ["warehouse_id"]

    @pytest.mark.asyncio
    async def test_execute_success(self, mock_env_client: AsyncMock) -> None:
        """Test successful execution."""
        tool = ListLocationsTool()

        mock_response = {
            "locations": [
                {"id": "L1", "warehouse_id": "WH1", "code": "A-01", "type": "shelf"},
                {"id": "L2", "warehouse_id": "WH1", "code": "B-01", "type": "bin"},
            ]
        }
        mock_env_client.list_locations.return_value = mock_response

        with patch(
            "app.tools.environment_tools.EnvironmentAPIClient", return_value=mock_env_client
        ):
            result = await tool.execute(warehouse_id="WH1", type="shelf")

            assert result == mock_response


class TestGetLocationsTreeTool:
    """Tests for GetLocationsTreeTool."""

    @pytest.mark.asyncio
    async def test_metadata(self) -> None:
        """Test tool metadata is correct."""
        tool = GetLocationsTreeTool()
        metadata = tool.get_metadata()

        assert metadata.name == "get_locations_tree"
        assert metadata.category == "environment"
        assert "tree" in metadata.description.lower()
        assert metadata.parameters["required"] == ["warehouse_id"]

    @pytest.mark.asyncio
    async def test_execute_success(self, mock_env_client: AsyncMock) -> None:
        """Test successful execution."""
        tool = GetLocationsTreeTool()

        mock_response = {
            "warehouse_id": "WH1",
            "tree": [
                {"id": "L1", "code": "A", "children": [{"id": "L2", "code": "A-01"}]},
            ],
        }
        mock_env_client.get_locations_tree.return_value = mock_response

        with patch(
            "app.tools.environment_tools.EnvironmentAPIClient", return_value=mock_env_client
        ):
            result = await tool.execute(warehouse_id="WH1")

            assert result == mock_response
            mock_env_client.get_locations_tree.assert_called_once_with(warehouse_id="WH1")


class TestGetCapacityUtilizationSnapshotTool:
    """Tests for GetCapacityUtilizationSnapshotTool."""

    @pytest.mark.asyncio
    async def test_metadata(self) -> None:
        """Test tool metadata is correct."""
        tool = GetCapacityUtilizationSnapshotTool()
        metadata = tool.get_metadata()

        assert metadata.name == "get_capacity_utilization_snapshot"
        assert metadata.category == "environment"
        assert "capacity" in metadata.description.lower()
        assert metadata.parameters["required"] == ["warehouse_id"]

    @pytest.mark.asyncio
    async def test_execute_success(self, mock_env_client: AsyncMock) -> None:
        """Test successful execution."""
        tool = GetCapacityUtilizationSnapshotTool()

        mock_response = {
            "locations": [
                {
                    "location_id": "L1",
                    "capacity_units": 1000,
                    "on_hand_sum": 750,
                    "utilization": 0.75,
                },
            ]
        }
        mock_env_client.get_capacity_utilization_snapshot.return_value = mock_response

        with patch(
            "app.tools.environment_tools.EnvironmentAPIClient", return_value=mock_env_client
        ):
            result = await tool.execute(warehouse_id="WH1")

            assert result == mock_response


# ========================================
# DEVICE MONITORING MODULE TESTS (4 tools)
# ========================================


class TestListSensorDevicesTool:
    """Tests for ListSensorDevicesTool."""

    @pytest.mark.asyncio
    async def test_metadata(self) -> None:
        """Test tool metadata is correct."""
        tool = ListSensorDevicesTool()
        metadata = tool.get_metadata()

        assert metadata.name == "list_sensor_devices"
        assert metadata.category == "environment"
        assert "sensor" in metadata.description.lower() or "device" in metadata.description.lower()
        assert metadata.skip_cache is True  # Real-time data

    @pytest.mark.asyncio
    async def test_execute_success(self, mock_env_client: AsyncMock) -> None:
        """Test successful execution."""
        tool = ListSensorDevicesTool()

        mock_response = {
            "devices": [
                {"id": "D1", "warehouse_id": "WH1", "device_type": "rfid", "status": "online"},
                {"id": "D2", "warehouse_id": "WH1", "device_type": "barcode", "status": "offline"},
            ]
        }
        mock_env_client.list_sensor_devices.return_value = mock_response

        with patch(
            "app.tools.environment_tools.EnvironmentAPIClient", return_value=mock_env_client
        ):
            result = await tool.execute(warehouse_id="WH1", status="online")

            assert result == mock_response


class TestGetDeviceHealthSummaryTool:
    """Tests for GetDeviceHealthSummaryTool."""

    @pytest.mark.asyncio
    async def test_metadata(self) -> None:
        """Test tool metadata is correct."""
        tool = GetDeviceHealthSummaryTool()
        metadata = tool.get_metadata()

        assert metadata.name == "get_device_health_summary"
        assert metadata.category == "environment"
        assert "health" in metadata.description.lower()

    @pytest.mark.asyncio
    async def test_execute_success(self, mock_env_client: AsyncMock) -> None:
        """Test successful execution."""
        tool = GetDeviceHealthSummaryTool()

        mock_response = {
            "total_devices": 50,
            "online": 45,
            "offline": 5,
            "avg_confidence": 0.92,
        }
        mock_env_client.get_device_health_summary.return_value = mock_response

        with patch(
            "app.tools.environment_tools.EnvironmentAPIClient", return_value=mock_env_client
        ):
            result = await tool.execute(warehouse_id="WH1")

            assert result == mock_response


class TestGetDeviceAnomaliesTool:
    """Tests for GetDeviceAnomaliesTool."""

    @pytest.mark.asyncio
    async def test_metadata(self) -> None:
        """Test tool metadata is correct."""
        tool = GetDeviceAnomaliesTool()
        metadata = tool.get_metadata()

        assert metadata.name == "get_device_anomalies"
        assert metadata.category == "environment"
        assert "anomal" in metadata.description.lower()

    @pytest.mark.asyncio
    async def test_execute_success(self, mock_env_client: AsyncMock) -> None:
        """Test successful execution."""
        tool = GetDeviceAnomaliesTool()

        mock_response = {
            "anomalies": [
                {"device_id": "D1", "type": "offline_but_producing", "severity": "high"},
                {"device_id": "D2", "type": "low_confidence", "severity": "medium"},
            ]
        }
        mock_env_client.get_device_anomalies.return_value = mock_response

        with patch(
            "app.tools.environment_tools.EnvironmentAPIClient", return_value=mock_env_client
        ):
            result = await tool.execute(warehouse_id="WH1", window=60)

            assert result == mock_response


# ========================================
# OBSERVED INVENTORY MODULE TESTS (1 tool)
# ========================================


class TestGetObservedInventorySnapshotTool:
    """Tests for GetObservedInventorySnapshotTool."""

    @pytest.mark.asyncio
    async def test_metadata(self) -> None:
        """Test tool metadata is correct."""
        tool = GetObservedInventorySnapshotTool()
        metadata = tool.get_metadata()

        assert metadata.name == "get_observed_inventory_snapshot"
        assert metadata.category == "environment"
        assert "observed" in metadata.description.lower()
        assert "quality_status_in" in metadata.parameters["properties"]
        assert metadata.skip_cache is True  # Real-time observations

    @pytest.mark.asyncio
    async def test_execute_success(self, mock_env_client: AsyncMock) -> None:
        """Test successful execution."""
        tool = GetObservedInventorySnapshotTool()

        mock_response = {
            "observations": [
                {
                    "product_id": "P1",
                    "location_id": "L1",
                    "observed_qty": 100,
                    "confidence": 0.95,
                    "quality_status": "good",
                },
            ]
        }
        mock_env_client.get_observed_inventory_snapshot.return_value = mock_response

        with patch(
            "app.tools.environment_tools.EnvironmentAPIClient", return_value=mock_env_client
        ):
            result = await tool.execute(quality_status_in=["good", "inspected"])

            assert result == mock_response
            mock_env_client.get_observed_inventory_snapshot.assert_called_once()


# ========================================
# INTEGRATION TESTS
# ========================================


class TestToolIntegration:
    """Integration tests for all environment tools."""

    @pytest.mark.asyncio
    async def test_all_tools_have_correct_category(self) -> None:
        """Test that all 21 tools have 'environment' category."""
        tools = [
            # Procurement (6)
            ListSuppliersTool(),
            GetSupplierTool(),
            ListPurchaseOrdersTool(),
            GetPurchaseOrderTool(),
            ListPOLinesTool(),
            GetProcurementPipelineSummaryTool(),
            # Inventory Audit (4)
            ListInventoryMovesTool(),
            GetInventoryMoveTool(),
            GetInventoryMoveAuditTraceTool(),
            GetInventoryAdjustmentsSummaryTool(),
            # Topology (6)
            ListWarehousesTool(),
            GetWarehouseTool(),
            ListLocationsTool(),
            GetLocationTool(),
            GetLocationsTreeTool(),
            GetCapacityUtilizationSnapshotTool(),
            # Device Monitoring (4)
            ListSensorDevicesTool(),
            GetSensorDeviceTool(),
            GetDeviceHealthSummaryTool(),
            GetDeviceAnomaliesTool(),
            # Observed Inventory (1)
            GetObservedInventorySnapshotTool(),
        ]

        assert len(tools) == 21  # Verify we have all 21 tools
        for tool in tools:
            assert tool.metadata.category == "environment"

    @pytest.mark.asyncio
    async def test_all_tools_have_openai_schemas(self) -> None:
        """Test that all tools can generate OpenAI function schemas."""
        tools = [
            ListSuppliersTool(),
            ListPurchaseOrdersTool(),
            ListInventoryMovesTool(),
            ListWarehousesTool(),
            ListSensorDevicesTool(),
            GetObservedInventorySnapshotTool(),
        ]

        for tool in tools:
            schema = tool.to_openai_function()
            assert schema["type"] == "function"
            assert "function" in schema
            assert "name" in schema["function"]
            assert "description" in schema["function"]
            assert "parameters" in schema["function"]


class TestParameterValidation:
    """Tests for parameter validation in tools."""

    @pytest.mark.asyncio
    async def test_missing_required_parameter_in_audit_trace(self) -> None:
        """Test that missing required parameter raises ValueError."""
        tool = GetInventoryMoveAuditTraceTool()

        with pytest.raises(ValueError, match="Missing required parameter.*move_id"):
            await tool.execute()  # Missing move_id

    @pytest.mark.asyncio
    async def test_missing_required_parameter_in_locations_tree(self) -> None:
        """Test missing required parameter in locations tree tool."""
        tool = GetLocationsTreeTool()

        with pytest.raises(ValueError, match="Missing required parameter.*warehouse_id"):
            await tool.execute()  # Missing warehouse_id
