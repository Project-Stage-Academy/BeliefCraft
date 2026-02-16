"""
HTTP client wrapper with automatic trace_id propagation and request logging.

This module provides a reusable HTTP client that automatically:
- Injects X-Request-ID headers from structlog context
- Logs all outgoing requests and responses
- Handles connection errors gracefully
- Supports async/await patterns

Usage:
    from common.http_client import TracedHttpClient

    async with TracedHttpClient("http://rag-service:8000") as client:
        response = await client.get("/api/documents/123")
        data = response.json()
"""

import time
from types import TracebackType
from typing import Any, TypedDict

import httpx
import structlog

logger = structlog.get_logger(__name__)


class HttpClientConfig(TypedDict, total=False):
    """Configuration for HTTP client (validated subset of httpx options)."""

    headers: dict[str, str]
    verify: bool
    follow_redirects: bool


class RequestLogger:
    """Handles HTTP request/response logging with trace_id propagation."""

    async def log_request(self, request: httpx.Request) -> None:
        """Add trace_id header and log outgoing request."""
        ctx = structlog.contextvars.get_contextvars()
        trace_id = ctx.get("trace_id", "internal-request")

        request.headers["X-Request-ID"] = trace_id
        request.extensions["start_time"] = time.perf_counter()

        logger.info(
            "http_request_started", method=request.method, url=str(request.url), trace_id=trace_id
        )

    async def log_response(self, response: httpx.Response) -> None:
        """Log response details. Only reads body for errors to prevent OOM."""
        start_time = response.request.extensions.get("start_time")
        if start_time is not None:
            duration_ms = (time.perf_counter() - start_time) * 1000
        else:
            # Fallback to httpx elapsed if start_time extension is missing
            try:
                duration_ms = response.elapsed.total_seconds() * 1000
            except RuntimeError:
                duration_ms = 0

        if response.status_code >= 400:
            await response.aread()
            logger.warning(
                "http_request_failed",
                status_code=response.status_code,
                method=response.request.method,
                url=str(response.request.url),
                duration_ms=duration_ms,
                response_body=response.text[:500],
            )
        else:
            logger.info(
                "http_request_completed",
                method=response.request.method,
                url=str(response.request.url),
                status_code=response.status_code,
                duration_ms=duration_ms,
            )


class TracedHttpClient:
    """
    HTTP client with automatic trace_id propagation and observability.

    This client wraps httpx.AsyncClient and automatically:
    - Adds X-Request-ID header from structlog context on every request
    - Logs request/response details with trace_id correlation
    - Provides clean async context manager interface

    Args:
        base_url: Target service URL (e.g., "http://rag-service:8000")
        timeout: Request timeout in seconds (default: 10.0)
        config: Optional validated configuration (headers, verify, follow_redirects)

    Example:
        async with TracedHttpClient("http://agent-service") as client:
            response = await client.post("/api/action", json={"query": "..."})
            logger.info("got_response", status=response.status_code)
    """

    def __init__(
        self, base_url: str, timeout: float = 10.0, config: HttpClientConfig | None = None
    ):
        self.base_url = base_url
        self.timeout = timeout
        self.config = config or {}
        self._client: httpx.AsyncClient | None = None
        self._request_logger = RequestLogger()

    async def __aenter__(self) -> "TracedHttpClient":
        """Initialize the HTTP client with event hooks."""
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            event_hooks={
                "request": [self._request_logger.log_request],
                "response": [self._request_logger.log_response],
            },
            **self.config,
        )
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Clean up the HTTP client connection pool."""
        if self._client:
            await self._client.aclose()

    def _ensure_initialized(self) -> httpx.AsyncClient:
        """Verify client is initialized before making requests."""
        if not self._client:
            raise RuntimeError("Client not initialized. Use 'async with' context manager.")
        return self._client

    async def get(self, url: str, **kwargs: Any) -> httpx.Response:
        """Send GET request with automatic trace_id propagation."""
        return await self._ensure_initialized().get(url, **kwargs)

    async def post(self, url: str, **kwargs: Any) -> httpx.Response:
        """Send POST request with automatic trace_id propagation."""
        return await self._ensure_initialized().post(url, **kwargs)

    async def put(self, url: str, **kwargs: Any) -> httpx.Response:
        """Send PUT request with automatic trace_id propagation."""
        return await self._ensure_initialized().put(url, **kwargs)

    async def delete(self, url: str, **kwargs: Any) -> httpx.Response:
        """Send DELETE request with automatic trace_id propagation."""
        return await self._ensure_initialized().delete(url, **kwargs)

    async def patch(self, url: str, **kwargs: Any) -> httpx.Response:
        """Send PATCH request with automatic trace_id propagation."""
        return await self._ensure_initialized().patch(url, **kwargs)


async def create_traced_client(
    base_url: str, timeout: float = 10.0, config: HttpClientConfig | None = None
) -> TracedHttpClient:
    """
    Factory function to create a traced HTTP client.

    Args:
        base_url: Target service URL
        timeout: Request timeout in seconds
        config: Optional validated configuration

    Returns:
        TracedHttpClient instance (remember to use 'async with')

    Example:
        client = await create_traced_client("http://rag-service:8000")
        async with client:
            response = await client.get("/health")
    """
    return TracedHttpClient(base_url, timeout, config)
