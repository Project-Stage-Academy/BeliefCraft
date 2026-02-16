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

    @pytest.mark.asyncio
    async def test_get_current_observations(self, mock_settings: Mock) -> None:
        """Test getting observations."""
        with patch("app.clients.environment_client.get_settings", return_value=mock_settings):
            client = EnvironmentAPIClient()

            with patch.object(client, "get", return_value={"inventory": []}) as mock_get:
                await client.get_current_observations(product_id="P1", location_id="L1")

                mock_get.assert_called_once_with(
                    "/observations/current",
                    params={"product_id": "P1", "location_id": "L1"},
                    timeout=None,
                )

    @pytest.mark.asyncio
    async def test_calculate_stockout_probability(self, mock_settings: Mock) -> None:
        """Test stockout probability calculation."""
        with patch("app.clients.environment_client.get_settings", return_value=mock_settings):
            client = EnvironmentAPIClient()

            with patch.object(client, "get", return_value={}) as mock_get:
                await client.calculate_stockout_probability("P1")
                mock_get.assert_called_once_with("/analysis/stockout-probability/P1")


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
            assert hasattr(client, "get_current_observations")
            assert hasattr(client, "get_inventory_history")
            assert hasattr(client, "get_order_backlog")
            assert hasattr(client, "get_shipments_in_transit")
            assert hasattr(client, "calculate_stockout_probability")
            assert hasattr(client, "calculate_lead_time_risk")

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
