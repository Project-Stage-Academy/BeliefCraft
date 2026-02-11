"""
FastAPI middleware for request tracing and logging.

Usage:
    from fastapi import FastAPI
    from common.middleware import setup_logging_middleware
    
    app = FastAPI()
    setup_logging_middleware(app)
"""

import time
import uuid
import structlog
from fastapi import FastAPI, Request, Response
from typing import Callable

logger = structlog.get_logger("infrastructure.middleware")

EXCLUDE_PATHS = {"/health", "/metrics", "/docs", "/openapi.json", "/redoc"}


def get_client_ip(request: Request) -> str:
    """
    Extract real client IP address (works behind proxies).
    
    Args:
        request: FastAPI Request object
    
    Returns:
        Client IP address or "unknown"
    """
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()

    return request.client.host if request.client else "unknown"


def setup_logging_middleware(app: FastAPI) -> None:
    """
    Setup HTTP request logging middleware with tracing.
    
    Features:
        - Automatic trace_id generation/propagation
        - Request/response logging
        - Performance metrics (duration)
        - Error tracking with stack traces
        - Client IP extraction (proxy-aware)
    
    Args:
        app: FastAPI application instance
    """
    
    @app.middleware("http")
    async def logging_middleware(request: Request, call_next: Callable) -> Response:
        raw_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        trace_id = raw_id[:64]

        structlog.contextvars.bind_contextvars(
            trace_id=trace_id,
            client_ip=get_client_ip(request),
            method=request.method,
            path=request.url.path,
        )

        start_time = time.time()
        
        try:
            if request.url.path not in EXCLUDE_PATHS:
                logger.debug(
                    "http_request_started",
                    user_agent=request.headers.get("User-Agent", "unknown"),
                )

            response: Response = await call_next(request)

            if request.url.path not in EXCLUDE_PATHS:
                duration = round((time.time() - start_time) * 1000, 2) 
                logger.info(
                    "http_request_finished",
                    status_code=response.status_code,
                    duration_ms=duration,
                )

            response.headers["X-Request-ID"] = trace_id
            return response

        except Exception as e:
            duration = round((time.time() - start_time) * 1000, 2)  # ms
            logger.error(
                "http_request_failed",
                error=str(e),
                error_type=type(e).__name__,
                duration_ms=duration,
                exc_info=True, 
            )
            raise
        
        finally:
            structlog.contextvars.clear_contextvars()
