"""
Unit tests for HTTP API clients.

Tests cover:
- BaseAPIClient with retry logic
- EnvironmentAPIClient methods
- RAGAPIClient methods
- Error handling and timeout behavior
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch
import httpx

from app.clients.base_client import BaseAPIClient
from app.clients.environment_client import EnvironmentAPIClient
from app.clients.rag_client import RAGAPIClient
from app.core.exceptions import ExternalServiceError


# Fixtures


@pytest.fixture
def mock_settings():
    """Mock settings for testing."""
    mock = Mock()
    mock.ENVIRONMENT_API_URL = "http://test-env-api:8000"
    mock.RAG_API_URL = "http://test-rag-api:8001"
    mock.TOOL_TIMEOUT_SECONDS = 30
    return mock


@pytest.fixture
def mock_traced_client():
    """Mock TracedHttpClient."""
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock()
    return client


# BaseAPIClient Tests


class TestBaseAPIClient:
    """Tests for BaseAPIClient."""
    
    @pytest.mark.asyncio
    async def test_client_initialization(self, mock_settings):
        """Test client initializes with correct config."""
        with patch("app.clients.base_client.get_settings", return_value=mock_settings):
            client = BaseAPIClient(
                base_url="http://test-api:8000",
                service_name="test-service"
            )
            
            assert client.base_url == "http://test-api:8000"
            assert client.service_name == "test-service"
            assert client.default_timeout == 30.0
            assert client._client is None  # Lazy initialization
    
    @pytest.mark.asyncio
    async def test_get_request_success(self, mock_settings, mock_traced_client):
        """Test successful GET request."""
        mock_response = Mock()
        mock_response.json.return_value = {"status": "ok"}
        mock_traced_client.get.return_value = mock_response
        
        with patch("app.clients.base_client.get_settings", return_value=mock_settings):
            with patch("app.clients.base_client.TracedHttpClient", return_value=mock_traced_client):
                client = BaseAPIClient("http://test", "test")
                async with client:
                    result = await client.get("/test", params={"key": "value"})
                
                assert result == {"status": "ok"}
                mock_traced_client.get.assert_called_once_with(
                    "/test",
                    params={"key": "value"}
                )
    
    @pytest.mark.asyncio
    async def test_post_request_success(self, mock_settings, mock_traced_client):
        """Test successful POST request."""
        mock_response = Mock()
        mock_response.json.return_value = {"created": True}
        mock_traced_client.post.return_value = mock_response
        
        with patch("app.clients.base_client.get_settings", return_value=mock_settings):
            with patch("app.clients.base_client.TracedHttpClient", return_value=mock_traced_client):
                client = BaseAPIClient("http://test", "test")
                async with client:
                    result = await client.post("/create", json={"name": "test"})
                
                assert result == {"created": True}
                mock_traced_client.post.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_http_status_error_raises_exception(self, mock_settings, mock_traced_client):
        """Test HTTP status errors are raised as ExternalServiceError."""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.text = "Not found"
        
        error = httpx.HTTPStatusError(
            message="Not found",
            request=Mock(),
            response=mock_response
        )
        mock_traced_client.get.side_effect = error
        
        with patch("app.clients.base_client.get_settings", return_value=mock_settings):
            with patch("app.clients.base_client.TracedHttpClient", return_value=mock_traced_client):
                client = BaseAPIClient("http://test", "test")
                async with client:
                    with pytest.raises(ExternalServiceError) as exc_info:
                        await client.get("/not-found")
                    
                    assert "returned HTTP 404" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_timeout_retries_then_fails(self, mock_settings, mock_traced_client):
        """Test timeout triggers retries before failing."""
        mock_traced_client.get.side_effect = httpx.TimeoutException("Timeout")
        
        with patch("app.clients.base_client.get_settings", return_value=mock_settings):
            with patch("app.clients.base_client.TracedHttpClient", return_value=mock_traced_client):
                client = BaseAPIClient("http://test", "test")
                async with client:
                    with pytest.raises(httpx.TimeoutException):
                        await client.get("/slow")
                    
                    # Should retry 3 times
                    assert mock_traced_client.get.call_count == 3
    
    @pytest.mark.asyncio
    async def test_network_error_retries(self, mock_settings, mock_traced_client):
        """Test network errors trigger retries."""
        mock_traced_client.get.side_effect = httpx.NetworkError("Connection refused")
        
        with patch("app.clients.base_client.get_settings", return_value=mock_settings):
            with patch("app.clients.base_client.TracedHttpClient", return_value=mock_traced_client):
                client = BaseAPIClient("http://test", "test")
                async with client:
                    with pytest.raises(httpx.NetworkError):
                        await client.get("/unreachable")
                    
                    assert mock_traced_client.get.call_count == 3


# EnvironmentAPIClient Tests


class TestEnvironmentAPIClient:
    """Tests for EnvironmentAPIClient."""
    
    @pytest.mark.asyncio
    async def test_get_current_observations_no_filters(self, mock_settings):
        """Test getting observations without filters."""
        mock_response = {"observations": [{"id": 1}, {"id": 2}]}
        
        with patch("app.clients.environment_client.get_settings", return_value=mock_settings):
            client = EnvironmentAPIClient()
            
            with patch.object(client, "get", return_value=mock_response) as mock_get:
                result = await client.get_current_observations()
                
                assert result == mock_response
                mock_get.assert_called_once_with("/observations/current", params={}, timeout=None)
    
    @pytest.mark.asyncio
    async def test_get_current_observations_with_filters(self, mock_settings):
        """Test getting observations with filters."""
        with patch("app.clients.environment_client.get_settings", return_value=mock_settings):
            client = EnvironmentAPIClient()
            
            with patch.object(client, "get", return_value={}) as mock_get:
                await client.get_current_observations(
                    product_id="P123",
                    location_id="L456",
                    warehouse_id="WH1"
                )
                
                mock_get.assert_called_once_with(
                    "/observations/current",
                    params={
                        "product_id": "P123",
                        "location_id": "L456",
                        "warehouse_id": "WH1"
                    },
                    timeout=None
                )
    
    @pytest.mark.asyncio
    async def test_get_inventory_history(self, mock_settings):
        """Test getting inventory history."""
        with patch("app.clients.environment_client.get_settings", return_value=mock_settings):
            client = EnvironmentAPIClient()
            
            with patch.object(client, "get", return_value={}) as mock_get:
                await client.get_inventory_history(product_id="P123", days=60)
                
                mock_get.assert_called_once_with(
                    "/inventory/history/P123",
                    params={"days": 60},
                    timeout=None
                )
    
    @pytest.mark.asyncio
    async def test_get_order_backlog(self, mock_settings):
        """Test getting order backlog."""
        with patch("app.clients.environment_client.get_settings", return_value=mock_settings):
            client = EnvironmentAPIClient()
            
            with patch.object(client, "get", return_value={}) as mock_get:
                await client.get_order_backlog(status="pending", priority="high")
                
                mock_get.assert_called_once_with(
                    "/orders/backlog",
                    params={"status": "pending", "priority": "high"}
                )
    
    @pytest.mark.asyncio
    async def test_get_shipments_in_transit(self, mock_settings):
        """Test getting shipments in transit."""
        with patch("app.clients.environment_client.get_settings", return_value=mock_settings):
            client = EnvironmentAPIClient()
            
            with patch.object(client, "get", return_value={}) as mock_get:
                await client.get_shipments_in_transit(warehouse_id="WH1")
                
                mock_get.assert_called_once_with(
                    "/shipments/in-transit",
                    params={"warehouse_id": "WH1"}
                )
    
    @pytest.mark.asyncio
    async def test_calculate_stockout_probability(self, mock_settings):
        """Test calculating stockout probability."""
        with patch("app.clients.environment_client.get_settings", return_value=mock_settings):
            client = EnvironmentAPIClient()
            
            with patch.object(client, "get", return_value={}) as mock_get:
                await client.calculate_stockout_probability(product_id="P123")
                
                mock_get.assert_called_once_with(
                    "/analysis/stockout-probability/P123"
                )
    
    @pytest.mark.asyncio
    async def test_calculate_lead_time_risk(self, mock_settings):
        """Test calculating lead time risk."""
        with patch("app.clients.environment_client.get_settings", return_value=mock_settings):
            client = EnvironmentAPIClient()
            
            with patch.object(client, "get", return_value={}) as mock_get:
                await client.calculate_lead_time_risk(
                    supplier_id="SUP123",
                    route_id="R456"
                )
                
                mock_get.assert_called_once_with(
                    "/analysis/lead-time-risk",
                    params={"supplier_id": "SUP123", "route_id": "R456"}
                )


# RAGAPIClient Tests


class TestRAGAPIClient:
    """Tests for RAGAPIClient."""
    
    @pytest.mark.asyncio
    async def test_search_knowledge_base_basic(self, mock_settings):
        """Test basic knowledge base search."""
        with patch("app.clients.rag_client.get_settings", return_value=mock_settings):
            client = RAGAPIClient()
            
            with patch.object(client, "post", return_value={}) as mock_post:
                await client.search_knowledge_base(query="inventory policy")
                
                mock_post.assert_called_once_with(
                    "/search/semantic",
                    json={
                        "query": "inventory policy",
                        "k": 5,
                        "traverse_types": [],
                        "filters": {}
                    },
                    timeout=None
                )
    
    @pytest.mark.asyncio
    async def test_search_knowledge_base_with_options(self, mock_settings):
        """Test knowledge base search with all options."""
        with patch("app.clients.rag_client.get_settings", return_value=mock_settings):
            client = RAGAPIClient()
            
            with patch.object(client, "post", return_value={}) as mock_post:
                await client.search_knowledge_base(
                    query="POMDP",
                    k=10,
                    traverse_types=["CITES", "REFERENCES"],
                    filters={"chapter": "16"}
                )
                
                mock_post.assert_called_once_with(
                    "/search/semantic",
                    json={
                        "query": "POMDP",
                        "k": 10,
                        "traverse_types": ["CITES", "REFERENCES"],
                        "filters": {"chapter": "16"}
                    },
                    timeout=None
                )
    
    @pytest.mark.asyncio
    async def test_expand_graph_by_ids(self, mock_settings):
        """Test graph expansion."""
        with patch("app.clients.rag_client.get_settings", return_value=mock_settings):
            client = RAGAPIClient()
            
            with patch.object(client, "post", return_value={}) as mock_post:
                await client.expand_graph_by_ids(
                    document_ids=["doc1", "doc2"],
                    traverse_types=["CITES"]
                )
                
                mock_post.assert_called_once_with(
                    "/search/expand-graph",
                    json={
                        "document_ids": ["doc1", "doc2"],
                        "traverse_types": ["CITES"]
                    }
                )
    
    @pytest.mark.asyncio
    async def test_get_entity_by_number(self, mock_settings):
        """Test getting entity by number."""
        with patch("app.clients.rag_client.get_settings", return_value=mock_settings):
            client = RAGAPIClient()
            
            with patch.object(client, "get", return_value={}) as mock_get:
                await client.get_entity_by_number(
                    entity_type="algorithm",
                    number="3.2"
                )
                
                mock_get.assert_called_once_with("/entity/algorithm/3.2")
