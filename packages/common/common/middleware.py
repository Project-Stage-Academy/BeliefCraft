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
from collections.abc import Awaitable, Callable

import structlog
from fastapi import FastAPI, Request, Response

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

    if request.client and request.client.host:
        return str(request.client.host)
    return "unknown"


def _should_log_request(path: str) -> bool:
    """Check if request path should be logged (DRY helper)."""
    return path not in EXCLUDE_PATHS


async def logging_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """
    HTTP request logging middleware with automatic tracing.

    Features:
    - Automatic trace_id generation/propagation
    - Request/response logging
    - Performance metrics (duration)
    - Error tracking with stack traces
    - Client IP extraction (proxy-aware)

    Args:
        request: Incoming HTTP request
        call_next: Next middleware/handler in chain

    Returns:
        HTTP response with X-Request-ID header
    """
    # Generate or extract trace_id with validation
    raw_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    if len(raw_id) > 64:
        logger.warning("trace_id_truncated", original_length=len(raw_id), truncated_to=64)
    trace_id = raw_id[:64]

    # Bind request context
    structlog.contextvars.bind_contextvars(
        trace_id=trace_id,
        client_ip=get_client_ip(request),
        method=request.method,
        path=request.url.path,
    )

    start_time = time.time()
    should_log = _should_log_request(request.url.path)

    try:
        if should_log:
            logger.debug(
                "http_request_started",
                user_agent=request.headers.get("User-Agent", "unknown"),
            )

        response: Response = await call_next(request)

        if should_log:
            duration = round((time.time() - start_time) * 1000, 2)
            logger.info(
                "http_request_finished",
                status_code=response.status_code,
                duration_ms=duration,
            )

        response.headers["X-Request-ID"] = trace_id
        return response

    except Exception as e:
        duration = round((time.time() - start_time) * 1000, 2)
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


def setup_logging_middleware(app: FastAPI) -> None:
    """
    Register logging middleware with FastAPI application.

    Args:
        app: FastAPI application instance
    """
    app.middleware("http")(logging_middleware)
