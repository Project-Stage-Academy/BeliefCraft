"""
Tests for TracedHttpClient with automatic trace_id propagation.

These tests verify:
- X-Request-ID header injection from structlog context
- Request/response logging with correlation
- Async context manager lifecycle
- HTTP method delegation (GET, POST, etc.)
"""

# mypy: disallow-untyped-defs=False, check-untyped-defs=False

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import structlog
from common.http_client import TracedHttpClient, create_traced_client


@pytest.fixture
def mock_httpx_client():
    """Mock httpx.AsyncClient for isolated testing."""
    with patch("common.http_client.httpx.AsyncClient") as mock_class:
        mock_instance = AsyncMock()
        mock_class.return_value = mock_instance
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"result": "ok"}'
        mock_response.elapsed.total_seconds.return_value = 0.123
        mock_response.request.method = "GET"
        mock_response.request.url = "http://test-service/api"

        mock_instance.get.return_value = mock_response
        mock_instance.post.return_value = mock_response
        mock_instance.put.return_value = mock_response
        mock_instance.delete.return_value = mock_response
        mock_instance.patch.return_value = mock_response
        mock_instance.aclose = AsyncMock()

        yield mock_instance


@pytest.mark.asyncio
async def test_traced_client_context_manager(mock_httpx_client):
    """Test async context manager properly initializes and closes client."""
    with patch("common.http_client.httpx.AsyncClient") as mock_class:
        mock_class.return_value = mock_httpx_client

        async with TracedHttpClient("http://test-service") as client:
            assert client._client is not None

        # Verify event hooks are registered (mentor feedback)
        call_kwargs = mock_class.call_args.kwargs
        assert "event_hooks" in call_kwargs
        hooks = call_kwargs["event_hooks"]
        assert "request" in hooks
        assert "response" in hooks
        assert len(hooks["request"]) == 1
        assert len(hooks["response"]) == 1

    mock_httpx_client.aclose.assert_called_once()


@pytest.mark.asyncio
async def test_trace_id_injection_from_context(caplog):
    """Test X-Request-ID header is injected from structlog contextvars."""

    structlog.contextvars.bind_contextvars(trace_id="test-trace-123")

    with patch("common.http_client.httpx.AsyncClient") as mock_class:
        mock_client = AsyncMock()
        mock_class.return_value = mock_client

        mock_request = MagicMock(spec=httpx.Request)
        mock_request.method = "GET"
        mock_request.url = "http://test/api"
        mock_request.headers = {}

        async with TracedHttpClient("http://test") as client:
            await client._request_logger.log_request(mock_request)

            assert mock_request.headers["X-Request-ID"] == "test-trace-123"

    structlog.contextvars.clear_contextvars()

    assert "http_request_started" in caplog.text
    assert "test-trace-123" in caplog.text


@pytest.mark.asyncio
async def test_default_trace_id_when_no_context(caplog):
    """Test default trace_id used when no contextvars present."""
    structlog.contextvars.clear_contextvars()

    with patch("common.http_client.httpx.AsyncClient") as mock_class:
        mock_client = AsyncMock()
        mock_class.return_value = mock_client

        mock_request = MagicMock(spec=httpx.Request)
        mock_request.method = "POST"
        mock_request.url = "http://test/create"
        mock_request.headers = {}

        async with TracedHttpClient("http://test") as client:
            await client._request_logger.log_request(mock_request)

            assert mock_request.headers["X-Request-ID"] == "internal-request"

    assert "internal-request" in caplog.text


@pytest.mark.asyncio
async def test_response_logging_success(caplog):
    """Test successful response is logged with duration."""
    with patch("common.http_client.httpx.AsyncClient") as mock_class:
        mock_client = AsyncMock()
        mock_class.return_value = mock_client

        mock_response = AsyncMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.text = '{"data": "value"}'
        mock_response.elapsed.total_seconds.return_value = 0.456
        mock_response.request.method = "GET"
        mock_response.request.url = "http://test/resource"

        async with TracedHttpClient("http://test") as client:
            await client._request_logger.log_response(mock_response)

    assert "http_request_completed" in caplog.text
    assert "200" in caplog.text
    assert "456" in caplog.text


@pytest.mark.asyncio
async def test_response_logging_error(caplog):
    """Test failed response logs warning with response body."""
    with patch("common.http_client.httpx.AsyncClient") as mock_class:
        mock_client = AsyncMock()
        mock_class.return_value = mock_client
        mock_response = AsyncMock(spec=httpx.Response)
        mock_response.status_code = 500
        mock_response.text = '{"error": "Internal Server Error"}'
        mock_response.elapsed.total_seconds.return_value = 0.123
        mock_response.request.method = "POST"
        mock_response.request.url = "http://test/action"

        async with TracedHttpClient("http://test") as client:
            await client._request_logger.log_response(mock_response)

    assert "http_request_failed" in caplog.text
    assert "500" in caplog.text
    assert "Internal Server Error" in caplog.text


@pytest.mark.asyncio
async def test_http_methods_delegation(mock_httpx_client):
    """Test all HTTP methods are properly delegated to httpx client."""
    async with TracedHttpClient("http://test") as client:
        await client.get("/resource")
        mock_httpx_client.get.assert_called_once_with("/resource")

        await client.post("/create", json={"key": "value"})
        mock_httpx_client.post.assert_called_once_with("/create", json={"key": "value"})

        await client.put("/update/123", json={"status": "updated"})
        mock_httpx_client.put.assert_called_once()

        await client.delete("/remove/456")
        mock_httpx_client.delete.assert_called_once_with("/remove/456")

        await client.patch("/partial/789", json={"field": "new"})
        mock_httpx_client.patch.assert_called_once()


@pytest.mark.asyncio
async def test_methods_raise_without_context_manager():
    """Test HTTP methods raise error when called outside context manager."""
    client = TracedHttpClient("http://test")

    with pytest.raises(RuntimeError, match="Client not initialized"):
        await client.get("/resource")

    with pytest.raises(RuntimeError, match="Client not initialized"):
        await client.post("/create")


@pytest.mark.asyncio
async def test_create_traced_client_factory():
    """Test convenience factory function creates proper client."""
    client = await create_traced_client(
        "http://factory-test", timeout=15.0, config={"verify": False}
    )

    assert isinstance(client, TracedHttpClient)
    assert client.base_url == "http://factory-test"
    assert client.timeout == 15.0
    assert client.config == {"verify": False}


@pytest.mark.asyncio
async def test_custom_timeout_configuration(mock_httpx_client):
    """Test custom timeout is passed to httpx client."""
    with patch("common.http_client.httpx.AsyncClient") as mock_class:
        mock_class.return_value = mock_httpx_client

        async with TracedHttpClient("http://test", timeout=30.0):
            pass

        mock_class.assert_called_once()
        call_kwargs = mock_class.call_args.kwargs
        assert call_kwargs["timeout"] == 30.0
        assert call_kwargs["base_url"] == "http://test"
