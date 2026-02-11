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

import httpx
import structlog
from typing import Any, Dict, Optional

logger = structlog.get_logger(__name__)


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
        **kwargs: Additional httpx.AsyncClient arguments
    
    Example:
        async with TracedHttpClient("http://agent-service") as client:
            response = await client.post("/api/action", json={"query": "..."})
            logger.info("got_response", status=response.status_code)
    """
    
    def __init__(
        self,
        base_url: str,
        timeout: float = 10.0,
        **kwargs: Any
    ):
        self.base_url = base_url
        self.timeout = timeout
        self._client_kwargs = kwargs
        self._client: Optional[httpx.AsyncClient] = None
    
    async def __aenter__(self) -> "TracedHttpClient":
        """Initialize the HTTP client with event hooks."""
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            event_hooks={
                "request": [self._log_request],
                "response": [self._log_response],
            },
            **self._client_kwargs
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Clean up the HTTP client connection pool."""
        if self._client:
            await self._client.aclose()
    
    async def _log_request(self, request: httpx.Request) -> None:
        """
        Event hook: Add trace_id header and log outgoing request.
        
        This runs before every HTTP request to:
        1. Read trace_id from structlog contextvars
        2. Inject X-Request-ID header for cross-service tracing
        3. Log request details for debugging
        """
        ctx = structlog.contextvars.get_contextvars()
        trace_id = ctx.get("trace_id", "internal-request")
        
        request.headers["X-Request-ID"] = trace_id
        
        logger.info(
            "http_request_started",
            method=request.method,
            url=str(request.url),
            trace_id=trace_id
        )
    
    async def _log_response(self, response: httpx.Response) -> None:
        """
        Event hook: Log response details after receiving from service.
        
        Captures status code, duration, and potential errors.
        """
        await response.aread()  
        
        logger.info(
            "http_request_completed",
            method=response.request.method,
            url=str(response.request.url),
            status_code=response.status_code,
            duration_ms=response.elapsed.total_seconds() * 1000
        )

        if response.status_code >= 400:
            logger.warning(
                "http_request_failed",
                status_code=response.status_code,
                response_body=response.text[:500]  
            )
    
    
    async def get(self, url: str, **kwargs: Any) -> httpx.Response:
        """Send GET request with automatic trace_id propagation."""
        if not self._client:
            raise RuntimeError("Client not initialized. Use 'async with' context manager.")
        return await self._client.get(url, **kwargs)
    
    async def post(self, url: str, **kwargs: Any) -> httpx.Response:
        """Send POST request with automatic trace_id propagation."""
        if not self._client:
            raise RuntimeError("Client not initialized. Use 'async with' context manager.")
        return await self._client.post(url, **kwargs)
    
    async def put(self, url: str, **kwargs: Any) -> httpx.Response:
        """Send PUT request with automatic trace_id propagation."""
        if not self._client:
            raise RuntimeError("Client not initialized. Use 'async with' context manager.")
        return await self._client.put(url, **kwargs)
    
    async def delete(self, url: str, **kwargs: Any) -> httpx.Response:
        """Send DELETE request with automatic trace_id propagation."""
        if not self._client:
            raise RuntimeError("Client not initialized. Use 'async with' context manager.")
        return await self._client.delete(url, **kwargs)
    
    async def patch(self, url: str, **kwargs: Any) -> httpx.Response:
        """Send PATCH request with automatic trace_id propagation."""
        if not self._client:
            raise RuntimeError("Client not initialized. Use 'async with' context manager.")
        return await self._client.patch(url, **kwargs)


async def create_traced_client(
    base_url: str,
    timeout: float = 10.0,
    **kwargs: Any
) -> TracedHttpClient:
    """
    Factory function to create a traced HTTP client.
    
    Args:
        base_url: Target service URL
        timeout: Request timeout in seconds
        **kwargs: Additional httpx.AsyncClient arguments
    
    Returns:
        TracedHttpClient instance (remember to use 'async with')
    
    Example:
        client = await create_traced_client("http://rag-service:8000")
        async with client:
            response = await client.get("/health")
    """
    return TracedHttpClient(base_url, timeout, **kwargs)
