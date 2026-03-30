"""
Unit tests for HTTP API clients.
"""

from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest
from app.clients.base_client import BaseAPIClient
from app.clients.environment_client import (
    EnvironmentAPIClient,
)
from app.core.exceptions import ExternalServiceError

# Fixtures


@pytest.fixture
def mock_settings() -> Mock:
    """Mock settings for testing matching the nested Pydantic schema."""
    mock = Mock()
    mock.external_services.environment_api_url = "http://test-env-api:8000"
    mock.external_services.rag_api_url = "http://test-rag-api:8001"
    mock.execution.tool_timeout_seconds = 30
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
        with patch("app.clients.base_client.settings", mock_settings):
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
            patch("app.clients.base_client.settings", mock_settings),
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
            patch("app.clients.base_client.settings", mock_settings),
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
            patch("app.clients.base_client.settings", mock_settings),
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
            patch("app.clients.base_client.settings", mock_settings),
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
        with patch("app.clients.environment_client.settings", mock_settings):
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
        with patch("app.clients.environment_client.settings", mock_settings):
            client = EnvironmentAPIClient()

            with patch.object(client, "get", return_value={}) as mock_get:
                await client.get_supplier("SUP1")
                mock_get.assert_called_once_with(
                    "/api/v1/smart-query/procurement/suppliers/SUP1", timeout=None
                )

    @pytest.mark.asyncio
    async def test_list_purchase_orders(self, mock_settings: Mock) -> None:
        """Test listing purchase orders."""
        with patch("app.clients.environment_client.settings", mock_settings):
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
    async def test_list_po_lines_preserves_repeated_purchase_order_ids(
        self, mock_settings: Mock
    ) -> None:
        """Test listing PO lines sends repeated query params for multiple PO ids."""
        with patch("app.clients.environment_client.settings", mock_settings):
            client = EnvironmentAPIClient()

            with patch.object(client, "get", return_value={"po_lines": []}) as mock_get:
                await client.list_po_lines(
                    purchase_order_ids=["PO-1", "PO-2"],
                )

                mock_get.assert_called_once_with(
                    "/api/v1/smart-query/procurement/po-lines",
                    params={"purchase_order_ids": ["PO-1", "PO-2"]},
                    timeout=None,
                )

    @pytest.mark.asyncio
    async def test_get_procurement_pipeline_summary(self, mock_settings: Mock) -> None:
        """Test getting procurement pipeline summary."""
        with patch("app.clients.environment_client.settings", mock_settings):
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
        with patch("app.clients.environment_client.settings", mock_settings):
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
        with patch("app.clients.environment_client.settings", mock_settings):
            client = EnvironmentAPIClient()

            with patch.object(client, "get", return_value={}) as mock_get:
                await client.get_inventory_move_audit_trace("M1")

                mock_get.assert_called_once_with(
                    "/api/v1/smart-query/inventory/moves/M1/audit-trace", timeout=None
                )

    @pytest.mark.asyncio
    async def test_get_inventory_adjustments_summary(self, mock_settings: Mock) -> None:
        """Test getting inventory adjustments summary."""
        with patch("app.clients.environment_client.settings", mock_settings):
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
        with patch("app.clients.environment_client.settings", mock_settings):
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
        with patch("app.clients.environment_client.settings", mock_settings):
            client = EnvironmentAPIClient()

            with patch.object(client, "get", return_value={"locations": []}):
                await client.list_locations(warehouse_id="WH1", type="shelf")
