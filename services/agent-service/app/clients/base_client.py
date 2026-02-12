"""
Base HTTP API client with retry logic and observability.

This module provides a base class for all external API clients with:
- Automatic trace_id propagation via TracedHttpClient
- Retry logic for transient failures (network errors, timeouts, 5xx errors)
- Structured logging for all requests
- Connection pooling and timeout management
- Singleton-like usage pattern to prevent connection leaks

Example:
    ```python
    # Use as singleton (recommended for FastAPI lifespan)
    env_client = EnvironmentAPIClient()
    
    async with env_client:
        obs = await env_client.get_current_observations()
    ```
"""

from typing import Any

import httpx
from common.http_client import TracedHttpClient
from common.logging import get_logger
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.config import get_settings
from app.core.exceptions import ExternalServiceError

logger = get_logger(__name__)

# HTTP status codes that should trigger retry
RETRYABLE_STATUS_CODES = {502, 503, 504}


class BaseAPIClient:
    """
    Base class for HTTP API clients with retry and timeout logic.
    
    Features:
    - Automatic retry on network errors and transient 5xx errors
    - Exponential backoff between retries (1-5 seconds)
    - Connection pooling for performance
    - Per-request timeout override support
    - Structured logging with trace_id
    - Lazy initialization to prevent connection leaks
    
    Important:
        Always use 'async with' context manager to properly manage connections.
        Recommended to use as application-level singleton to share connection pool.
    
    Attributes:
        base_url: API base URL
        service_name: Name for logging and error messages
        default_timeout: Default timeout in seconds
    """
    
    def __init__(self, base_url: str, service_name: str) -> None:
        """
        Initialize API client.
        
        Args:
            base_url: Base URL for the API (e.g., "http://environment-api:8000")
            service_name: Service name for logging (e.g., "environment-api")
        """
        self.base_url = base_url.rstrip("/")
        self.service_name = service_name
        
        settings = get_settings()
        self.default_timeout = float(settings.TOOL_TIMEOUT_SECONDS)
        
        # Lazy initialization - client created only in __aenter__
        self._client: TracedHttpClient | None = None
        
        logger.debug(
            "api_client_initialized",
            service=self.service_name,
            base_url=self.base_url,
            default_timeout=self.default_timeout
        )
    
    async def __aenter__(self) -> "BaseAPIClient":
        """
        Enter async context manager and initialize HTTP client.
        
        This creates the TracedHttpClient with connection pooling.
        """
        self._client = TracedHttpClient(
            base_url=self.base_url,
            timeout=self.default_timeout
        )
        await self._client.__aenter__()
        
        logger.debug(
            "api_client_connected",
            service=self.service_name
        )
        
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:  # type: ignore
        """
        Exit async context manager and close HTTP client.
        
        This properly closes all connections in the pool.
        """
        if self._client:
            await self._client.__aexit__(exc_type, exc_val, exc_tb)
        
        logger.debug(
            "api_client_disconnected",
            service=self.service_name
        )
    
    def _should_retry_status_code(self, status_code: int) -> bool:
        """
        Check if HTTP status code should trigger retry.
        
        Retryable codes:
        - 502 Bad Gateway (upstream server error)
        - 503 Service Unavailable (temporary overload)
        - 504 Gateway Timeout (upstream timeout)
        
        Args:
            status_code: HTTP status code
        
        Returns:
            True if should retry
        """
        return status_code in RETRYABLE_STATUS_CODES
    
    async def _make_request_with_retry(
        self,
        method: str,
        endpoint: str,
        timeout: float | None = None,
        **kwargs: Any
    ) -> dict[str, Any]:
        """
        Make HTTP request with automatic retry logic.
        
        Retries on:
        - httpx.TimeoutException (connection/read timeouts)
        - httpx.NetworkError (DNS failures, connection refused)
        - HTTP 502, 503, 504 (transient gateway/server errors)
        
        Does NOT retry on:
        - HTTP 4xx errors (client errors - fix the request first)
        - HTTP 500, 501, 505+ (likely permanent server issues)
        
        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            endpoint: API endpoint path
            timeout: Optional timeout override (seconds)
            **kwargs: Additional arguments for httpx (params, json, headers, etc.)
        
        Returns:
            Parsed JSON response as dictionary
        
        Raises:
            ExternalServiceError: On HTTP errors or after retry exhaustion
            RuntimeError: If client not initialized (forgot 'async with')
        """
        if not self._client:
            raise RuntimeError(
                f"{self.service_name} client not initialized. "
                "Use 'async with' context manager."
            )
        
        # Override timeout if specified
        if timeout:
            kwargs["timeout"] = timeout
        
        attempt_number = 0
        
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=1, max=5),
            retry=retry_if_exception_type((
                httpx.TimeoutException,
                httpx.NetworkError
            )),
            reraise=True
        ):
            with attempt:
                attempt_number += 1
                
                try:
                    logger.debug(
                        "api_request_attempt",
                        service=self.service_name,
                        method=method,
                        endpoint=endpoint,
                        attempt=attempt_number,
                        timeout=timeout or self.default_timeout,
                        **{k: v for k, v in kwargs.items() if k in ["params"]}
                    )
                    
                    # Use appropriate HTTP method from TracedHttpClient
                    if method == "GET":
                        response = await self._client.get(endpoint, **kwargs)
                    elif method == "POST":
                        response = await self._client.post(endpoint, **kwargs)
                    elif method == "PUT":
                        response = await self._client.put(endpoint, **kwargs)
                    elif method == "DELETE":
                        response = await self._client.delete(endpoint, **kwargs)
                    else:
                        raise ValueError(f"Unsupported HTTP method: {method}")
                    
                    # Check for retryable 5xx errors
                    if self._should_retry_status_code(response.status_code):
                        logger.warning(
                            "api_retryable_status",
                            service=self.service_name,
                            method=method,
                            endpoint=endpoint,
                            status_code=response.status_code,
                            attempt=attempt_number
                        )
                        
                        # Manually raise to trigger retry
                        raise httpx.HTTPStatusError(
                            message=f"Retryable status {response.status_code}",
                            request=response.request,
                            response=response
                        )
                    
                    # Raise for other 4xx/5xx status codes
                    response.raise_for_status()
                    
                    # Parse JSON response
                    return response.json()
                
                except httpx.HTTPStatusError as e:
                    # Check if it's a retryable error we just raised
                    if self._should_retry_status_code(e.response.status_code):
                        # Let tenacity handle retry
                        raise httpx.NetworkError("Retryable server error")
                    
                    # Non-retryable HTTP error - log and raise immediately
                    logger.error(
                        "api_http_error",
                        service=self.service_name,
                        method=method,
                        endpoint=endpoint,
                        status_code=e.response.status_code,
                        exc_info=True
                    )
                    
                    raise ExternalServiceError(
                        f"{self.service_name} returned HTTP {e.response.status_code}",
                        service_name=self.service_name
                    )
                
                except (httpx.TimeoutException, httpx.NetworkError) as e:
                    # These will be retried by tenacity
                    logger.warning(
                        "api_transient_error",
                        service=self.service_name,
                        method=method,
                        endpoint=endpoint,
                        attempt=attempt_number,
                        error=str(e),
                        error_type=type(e).__name__
                    )
                    raise  # Let tenacity handle retry
                
                except Exception as e:
                    # Unexpected errors - don't retry
                    logger.error(
                        "api_unexpected_error",
                        service=self.service_name,
                        method=method,
                        endpoint=endpoint,
                        error=str(e),
                        error_type=type(e).__name__,
                        exc_info=True
                    )
                    
                    raise ExternalServiceError(
                        f"{self.service_name} error: {str(e)}",
                        service_name=self.service_name
                    )
        
        # This should never be reached due to reraise=True
        raise ExternalServiceError(
            f"{self.service_name} request failed after retries",
            service_name=self.service_name
        )
    
    async def get(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
        timeout: float | None = None
    ) -> dict[str, Any]:
        """
        Perform GET request with retry logic.
        
        Args:
            endpoint: API endpoint (e.g., "/observations/current")
            params: Optional query parameters
            timeout: Optional timeout override in seconds
        
        Returns:
            Parsed JSON response
        """
        return await self._make_request_with_retry(
            "GET",
            endpoint,
            timeout=timeout,
            params=params
        )
    
    async def post(
        self,
        endpoint: str,
        json: dict[str, Any] | None = None,
        timeout: float | None = None
    ) -> dict[str, Any]:
        """
        Perform POST request with retry logic.
        
        Args:
            endpoint: API endpoint
            json: Optional JSON body
            timeout: Optional timeout override in seconds
        
        Returns:
            Parsed JSON response
        """
        return await self._make_request_with_retry(
            "POST",
            endpoint,
            timeout=timeout,
            json=json
        )
    
    async def put(
        self,
        endpoint: str,
        json: dict[str, Any] | None = None,
        timeout: float | None = None
    ) -> dict[str, Any]:
        """
        Perform PUT request with retry logic.
        
        Args:
            endpoint: API endpoint
            json: Optional JSON body
            timeout: Optional timeout override in seconds
        
        Returns:
            Parsed JSON response
        """
        return await self._make_request_with_retry(
            "PUT",
            endpoint,
            timeout=timeout,
            json=json
        )
    
    async def delete(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
        timeout: float | None = None
    ) -> dict[str, Any]:
        """
        Perform DELETE request with retry logic.
        
        Args:
            endpoint: API endpoint
            params: Optional query parameters
            timeout: Optional timeout override in seconds
        
        Returns:
            Parsed JSON response
        """
        return await self._make_request_with_retry(
            "DELETE",
            endpoint,
            timeout=timeout,
            params=params
        )


