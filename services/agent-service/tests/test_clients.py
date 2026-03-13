"""
Unit tests for HTTP API clients.
"""

from typing import cast
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest
from app.clients.base_client import BaseAPIClient
from app.clients.environment_client import (
    EnvironmentAPIClient,
    EnvironmentClientProtocol,
)
from app.clients.rag_client import RAGAPIClient, RAGClientProtocol
from app.core.exceptions import ExternalServiceError

# Fixtures


@pytest.fixture
def mock_settings() -> Mock:
    """Mock settings for testing."""
    mock = Mock()
    mock.ENVIRONMENT_API_URL = "http://test-env-api:8000"
    mock.RAG_API_URL = "http://test-rag-api:8001"
    mock.TOOL_TIMEOUT_SECONDS = 30
    return mock


@pytest.fixture
def mock_traced_client() -> AsyncMock:
    """Mock TracedHttpClient."""
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock()
    return client


# BaseAPIClient Tests


class TestBaseAPIClient:
    """Tests for BaseAPIClient."""

    @pytest.mark.asyncio
    async def test_client_initialization(self, mock_settings: Mock) -> None:
        """Test client initialization with settings."""
        with patch("app.clients.base_client.get_settings", return_value=mock_settings):
            client = BaseAPIClient("http://api.test", "test-api")
            assert client.base_url == "http://api.test"
            assert client.service_name == "test-api"
            assert client.default_timeout == 30.0

    @pytest.mark.asyncio
    async def test_context_manager(
        self, mock_settings: Mock, mock_traced_client: AsyncMock
    ) -> None:
        """Test async context manager lifecycle."""
        with (
            patch("app.clients.base_client.get_settings", return_value=mock_settings),
            patch("app.clients.base_client.TracedHttpClient", return_value=mock_traced_client),
        ):
            client = BaseAPIClient("http://api.test", "test-api")
            async with client as connected_client:
                assert connected_client == client
                mock_traced_client.__aenter__.assert_called_once()

            mock_traced_client.__aexit__.assert_called_once()

    @pytest.mark.asyncio
    async def test_make_request_success(
        self, mock_settings: Mock, mock_traced_client: AsyncMock
    ) -> None:
        """Test successful request with retry logic."""
        with (
            patch("app.clients.base_client.get_settings", return_value=mock_settings),
            patch("app.clients.base_client.TracedHttpClient", return_value=mock_traced_client),
        ):
            client = BaseAPIClient("http://api.test", "test-api")

            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"status": "ok"}
            mock_traced_client.get.return_value = mock_response

            async with client:
                result = await client.get("/test")
                assert result == {"status": "ok"}

    @pytest.mark.asyncio
    async def test_retry_on_502(self, mock_settings: Mock, mock_traced_client: AsyncMock) -> None:
        """Test retry logic on 502 Bad Gateway."""
        with (
            patch("app.clients.base_client.get_settings", return_value=mock_settings),
            patch("app.clients.base_client.TracedHttpClient", return_value=mock_traced_client),
        ):
            client = BaseAPIClient("http://api.test", "test-api")

            # First call 502, second call 200
            mock_502 = Mock()
            mock_502.status_code = 502

            mock_200 = Mock()
            mock_200.status_code = 200
            mock_200.json.return_value = {"success": True}

            mock_traced_client.get.side_effect = [mock_502, mock_200]

            async with client:
                result = await client.get("/test")
                assert result == {"success": True}
                assert mock_traced_client.get.call_count == 2

    @pytest.mark.asyncio
    async def test_external_service_error(
        self, mock_settings: Mock, mock_traced_client: AsyncMock
    ) -> None:
        """Test non-retryable 404 error."""
        with (
            patch("app.clients.base_client.get_settings", return_value=mock_settings),
            patch("app.clients.base_client.TracedHttpClient", return_value=mock_traced_client),
        ):
            client = BaseAPIClient("http://api.test", "test-api")

            mock_404 = Mock()
            mock_404.status_code = 404
            mock_traced_client.get.return_value = mock_404

            # Mock raise_for_status to actually raise
            mock_404.raise_for_status.side_effect = httpx.HTTPStatusError(
                "Not Found", request=Mock(), response=mock_404
            )

            async with client:
                with pytest.raises(ExternalServiceError) as exc:
                    await client.get("/nonexistent")
                assert "404" in str(exc.value)


class TestEnvironmentAPIClient:
    """Tests for EnvironmentAPIClient."""

    # PROCUREMENT MODULE TESTS

    @pytest.mark.asyncio
    async def test_list_suppliers(self, mock_settings: Mock) -> None:
        """Test listing suppliers."""
        with patch("app.clients.environment_client.get_settings", return_value=mock_settings):
            client = EnvironmentAPIClient()

            with patch.object(client, "get", return_value={"suppliers": []}) as mock_get:
                await client.list_suppliers(region="US", reliability_min=0.9)

                mock_get.assert_called_once_with(
                    "/api/v1/smart-query/procurement/suppliers",
                    params={"region": "US", "reliability_min": 0.9},
                    timeout=None,
                )

    @pytest.mark.asyncio
    async def test_get_supplier(self, mock_settings: Mock) -> None:
        """Test getting a specific supplier."""
        with patch("app.clients.environment_client.get_settings", return_value=mock_settings):
            client = EnvironmentAPIClient()

            with patch.object(client, "get", return_value={}) as mock_get:
                await client.get_supplier("SUP1")
                mock_get.assert_called_once_with(
                    "/api/v1/smart-query/procurement/suppliers/SUP1", timeout=None
                )

    @pytest.mark.asyncio
    async def test_list_purchase_orders(self, mock_settings: Mock) -> None:
        """Test listing purchase orders."""
        with patch("app.clients.environment_client.get_settings", return_value=mock_settings):
            client = EnvironmentAPIClient()

            with patch.object(client, "get", return_value={"purchase_orders": []}) as mock_get:
                await client.list_purchase_orders(
                    supplier_id="SUP1", status_in=["pending", "confirmed"]
                )

                mock_get.assert_called_once_with(
                    "/api/v1/smart-query/procurement/purchase-orders",
                    params={"supplier_id": "SUP1", "status_in": ["pending", "confirmed"]},
                    timeout=None,
                )

    @pytest.mark.asyncio
    async def test_get_procurement_pipeline_summary(self, mock_settings: Mock) -> None:
        """Test getting procurement pipeline summary."""
        with patch("app.clients.environment_client.get_settings", return_value=mock_settings):
            client = EnvironmentAPIClient()

            with patch.object(client, "get", return_value={}) as mock_get:
                await client.get_procurement_pipeline_summary(destination_warehouse_id="WH1")

                mock_get.assert_called_once_with(
                    "/api/v1/smart-query/procurement/pipeline-summary",
                    params={"destination_warehouse_id": "WH1"},
                    timeout=None,
                )

    # INVENTORY AUDIT MODULE TESTS

    @pytest.mark.asyncio
    async def test_list_inventory_moves(self, mock_settings: Mock) -> None:
        """Test listing inventory moves."""
        with patch("app.clients.environment_client.get_settings", return_value=mock_settings):
            client = EnvironmentAPIClient()

            with patch.object(client, "get", return_value={"moves": []}) as mock_get:
                await client.list_inventory_moves(warehouse_id="WH1", move_type="adjustment")

                mock_get.assert_called_once_with(
                    "/api/v1/smart-query/inventory/moves",
                    params={"warehouse_id": "WH1", "move_type": "adjustment"},
                    timeout=None,
                )

    @pytest.mark.asyncio
    async def test_get_inventory_move_audit_trace(self, mock_settings: Mock) -> None:
        """Test getting inventory move audit trace."""
        with patch("app.clients.environment_client.get_settings", return_value=mock_settings):
            client = EnvironmentAPIClient()

            with patch.object(client, "get", return_value={}) as mock_get:
                await client.get_inventory_move_audit_trace("M1")

                mock_get.assert_called_once_with(
                    "/api/v1/smart-query/inventory/moves/M1/audit-trace", timeout=None
                )

    @pytest.mark.asyncio
    async def test_get_inventory_adjustments_summary(self, mock_settings: Mock) -> None:
        """Test getting inventory adjustments summary."""
        with patch("app.clients.environment_client.get_settings", return_value=mock_settings):
            client = EnvironmentAPIClient()

            with patch.object(client, "get", return_value={}) as mock_get:
                await client.get_inventory_adjustments_summary(warehouse_id="WH1", product_id="P1")

                mock_get.assert_called_once_with(
                    "/api/v1/smart-query/inventory/adjustments-summary",
                    params={"warehouse_id": "WH1", "product_id": "P1"},
                    timeout=None,
                )

    # TOPOLOGY MODULE TESTS

    @pytest.mark.asyncio
    async def test_list_warehouses(self, mock_settings: Mock) -> None:
        """Test listing warehouses."""
        with patch("app.clients.environment_client.get_settings", return_value=mock_settings):
            client = EnvironmentAPIClient()

            with patch.object(client, "get", return_value={"warehouses": []}) as mock_get:
                await client.list_warehouses(region="US")

                mock_get.assert_called_once_with(
                    "/api/v1/smart-query/topology/warehouses",
                    params={"region": "US"},
                    timeout=None,
                )

    @pytest.mark.asyncio
    async def test_list_locations(self, mock_settings: Mock) -> None:
        """Test listing locations."""
        with patch("app.clients.environment_client.get_settings", return_value=mock_settings):
            client = EnvironmentAPIClient()

            with patch.object(client, "get", return_value={"locations": []}) as mock_get:
                await client.list_locations(warehouse_id="WH1", type="shelf")

                mock_get.assert_called_once_with(
                    "/api/v1/smart-query/topology/locations",
                    params={"warehouse_id": "WH1", "type": "shelf"},
                    timeout=None,
                )

    @pytest.mark.asyncio
    async def test_get_locations_tree(self, mock_settings: Mock) -> None:
        """Test getting locations tree."""
        with patch("app.clients.environment_client.get_settings", return_value=mock_settings):
            client = EnvironmentAPIClient()

            with patch.object(client, "get", return_value={}) as mock_get:
                await client.get_locations_tree("WH1")

                mock_get.assert_called_once_with(
                    "/api/v1/smart-query/topology/warehouses/WH1/locations-tree", timeout=None
                )

    @pytest.mark.asyncio
    async def test_get_capacity_utilization_snapshot(self, mock_settings: Mock) -> None:
        """Test getting capacity utilization snapshot."""
        with patch("app.clients.environment_client.get_settings", return_value=mock_settings):
            client = EnvironmentAPIClient()

            with patch.object(client, "get", return_value={}) as mock_get:
                await client.get_capacity_utilization_snapshot(warehouse_id="WH1", type="shelf")

                mock_get.assert_called_once_with(
                    "/api/v1/smart-query/topology/warehouses/WH1/capacity-utilization",
                    params={"type": "shelf"},
                    timeout=None,
                )

    # DEVICE MONITORING MODULE TESTS

    @pytest.mark.asyncio
    async def test_list_sensor_devices(self, mock_settings: Mock) -> None:
        """Test listing sensor devices."""
        with patch("app.clients.environment_client.get_settings", return_value=mock_settings):
            client = EnvironmentAPIClient()

            with patch.object(client, "get", return_value={"devices": []}) as mock_get:
                await client.list_sensor_devices(warehouse_id="WH1", status="online")

                mock_get.assert_called_once_with(
                    "/api/v1/smart-query/devices",
                    params={"warehouse_id": "WH1", "status": "online"},
                    timeout=None,
                )

    @pytest.mark.asyncio
    async def test_get_device_health_summary(self, mock_settings: Mock) -> None:
        """Test getting device health summary."""
        with patch("app.clients.environment_client.get_settings", return_value=mock_settings):
            client = EnvironmentAPIClient()

            with patch.object(client, "get", return_value={}) as mock_get:
                await client.get_device_health_summary(warehouse_id="WH1")

                mock_get.assert_called_once_with(
                    "/api/v1/smart-query/devices/health-summary",
                    params={"warehouse_id": "WH1"},
                    timeout=None,
                )

    @pytest.mark.asyncio
    async def test_get_device_anomalies(self, mock_settings: Mock) -> None:
        """Test getting device anomalies."""
        with patch("app.clients.environment_client.get_settings", return_value=mock_settings):
            client = EnvironmentAPIClient()

            with patch.object(client, "get", return_value={}) as mock_get:
                await client.get_device_anomalies(warehouse_id="WH1", window=60)

                mock_get.assert_called_once_with(
                    "/api/v1/smart-query/devices/anomalies",
                    params={"warehouse_id": "WH1", "window": 60},
                    timeout=None,
                )

    # OBSERVED INVENTORY MODULE TESTS

    @pytest.mark.asyncio
    async def test_get_observed_inventory_snapshot(self, mock_settings: Mock) -> None:
        """Test getting observed inventory snapshot."""
        with patch("app.clients.environment_client.get_settings", return_value=mock_settings):
            client = EnvironmentAPIClient()

            with patch.object(client, "get", return_value={}) as mock_get:
                await client.get_observed_inventory_snapshot(
                    quality_status_in=["good", "inspected"]
                )

                mock_get.assert_called_once_with(
                    "/api/v1/smart-query/inventory/current",
                    params={"quality_status_in": "good,inspected"},
                    timeout=None,
                )


class TestRAGAPIClient:
    """Tests for RAGAPIClient."""

    @pytest.mark.asyncio
    async def test_search_knowledge_base(self, mock_settings: Mock) -> None:
        """Test semantic search."""
        with patch("app.clients.rag_client.get_settings", return_value=mock_settings):
            client = RAGAPIClient()

            with patch.object(client, "post", return_value=[]) as mock_post:
                await client.search_knowledge_base(
                    query="POMDP",
                    k=10,
                    traverse_types=["CITES", "REFERENCES"],
                    filters={"chapter": "16"},
                )

                mock_post.assert_called_once_with(
                    "/search/semantic",
                    json={
                        "query": "POMDP",
                        "k": 10,
                        "traverse_types": ["CITES", "REFERENCES"],
                        "filters": {"chapter": "16"},
                    },
                    timeout=None,
                )

    @pytest.mark.asyncio
    async def test_expand_graph_by_ids(self, mock_settings: Mock) -> None:
        """Test graph expansion."""
        with patch("app.clients.rag_client.get_settings", return_value=mock_settings):
            client = RAGAPIClient()

            with patch.object(client, "post", return_value={}) as mock_post:
                await client.expand_graph_by_ids(
                    document_ids=["doc1", "doc2"], traverse_types=["CITES"]
                )

                mock_post.assert_called_once_with(
                    "/search/expand-graph",
                    json={"document_ids": ["doc1", "doc2"], "traverse_types": ["CITES"]},
                )

    @pytest.mark.asyncio
    async def test_get_entity_by_number(self, mock_settings: Mock) -> None:
        """Test getting entity by number."""
        with patch("app.clients.rag_client.get_settings", return_value=mock_settings):
            client = RAGAPIClient()

            with patch.object(client, "get", return_value={}) as mock_get:
                await client.get_entity_by_number(entity_type="algorithm", number="3.2")
                mock_get.assert_called_once_with("/entity/algorithm/3.2")


class TestProtocolCompliance:
    """Tests that clients comply with their Protocol definitions."""

    @pytest.mark.asyncio
    async def test_environment_client_implements_protocol(self, mock_settings: Mock) -> None:
        """Test EnvironmentAPIClient implements EnvironmentClientProtocol."""
        with patch("app.clients.environment_client.get_settings", return_value=mock_settings):
            client: EnvironmentClientProtocol = cast(
                EnvironmentClientProtocol, EnvironmentAPIClient()
            )

            # Check that client has all required methods
            assert hasattr(client, "__aenter__")
            assert hasattr(client, "__aexit__")

            # Procurement module methods
            assert hasattr(client, "list_suppliers")
            assert hasattr(client, "get_supplier")
            assert hasattr(client, "list_purchase_orders")
            assert hasattr(client, "get_purchase_order")
            assert hasattr(client, "list_po_lines")
            assert hasattr(client, "get_procurement_pipeline_summary")

            # Inventory audit module methods
            assert hasattr(client, "list_inventory_moves")
            assert hasattr(client, "get_inventory_move")
            assert hasattr(client, "get_inventory_move_audit_trace")
            assert hasattr(client, "get_inventory_adjustments_summary")

            # Topology module methods
            assert hasattr(client, "list_warehouses")
            assert hasattr(client, "get_warehouse")
            assert hasattr(client, "list_locations")
            assert hasattr(client, "get_location")
            assert hasattr(client, "get_locations_tree")
            assert hasattr(client, "get_capacity_utilization_snapshot")

            # Device monitoring module methods
            assert hasattr(client, "list_sensor_devices")
            assert hasattr(client, "get_sensor_device")
            assert hasattr(client, "get_device_health_summary")
            assert hasattr(client, "get_device_anomalies")

            # Observed inventory module methods
            assert hasattr(client, "get_observed_inventory_snapshot")

    @pytest.mark.asyncio
    async def test_rag_client_implements_protocol(self, mock_settings: Mock) -> None:
        """Test RAGAPIClient implements RAGClientProtocol."""
        with patch("app.clients.rag_client.get_settings", return_value=mock_settings):
            client: RAGClientProtocol = cast(RAGClientProtocol, RAGAPIClient())

            # Check that client has all required methods
            assert hasattr(client, "__aenter__")
            assert hasattr(client, "__aexit__")
            assert hasattr(client, "search_knowledge_base")
            assert hasattr(client, "expand_graph_by_ids")
            assert hasattr(client, "get_entity_by_number")


# RAGMCPClient Tests


class TestRAGMCPClient:
    """Tests for RAGMCPClient validation and initialization."""

    def test_rag_mcp_client_empty_base_url(self) -> None:
        """Test RAGMCPClient rejects empty base_url."""
        from app.clients.rag_mcp_client import RAGMCPClient

        with pytest.raises(ValueError, match="base_url cannot be empty"):
            RAGMCPClient("")

    def test_rag_mcp_client_whitespace_base_url(self) -> None:
        """Test RAGMCPClient rejects whitespace-only base_url."""
        from app.clients.rag_mcp_client import RAGMCPClient

        with pytest.raises(ValueError, match="base_url cannot be empty or whitespace-only"):
            RAGMCPClient("   ")

    def test_rag_mcp_client_strips_whitespace(self) -> None:
        """Test RAGMCPClient strips leading/trailing whitespace from base_url."""
        from app.clients.rag_mcp_client import RAGMCPClient

        client = RAGMCPClient("  http://localhost:8001  ")
        assert client.base_url == "http://localhost:8001"

    def test_rag_mcp_client_strips_trailing_slash(self) -> None:
        """Test RAGMCPClient strips trailing slash from base_url."""
        from app.clients.rag_mcp_client import RAGMCPClient

        client = RAGMCPClient("http://localhost:8001/")
        assert client.base_url == "http://localhost:8001"
