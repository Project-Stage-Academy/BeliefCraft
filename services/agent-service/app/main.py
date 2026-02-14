import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

import httpx
import redis
import structlog
from app.api.v1.routes import health
from app.config import get_settings
from app.core.constants import HEALTH_CHECK_TIMEOUT
from app.core.exceptions import AgentServiceException
from app.core.logging import configure_logging
from app.services.health_checker import HealthChecker
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Configure logging
logger = configure_logging()

# Initialize FastAPI
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan manager"""
    # Startup
    logger.info("agent_service_starting", version=settings.SERVICE_VERSION)
    app.state.http_client = httpx.AsyncClient(timeout=HEALTH_CHECK_TIMEOUT)
    app.state.redis_pool = redis.ConnectionPool.from_url(settings.REDIS_URL, decode_responses=True)
    app.state.redis_client = redis.Redis(connection_pool=app.state.redis_pool)
    yield
    # Shutdown
    await app.state.http_client.aclose()
    app.state.redis_client.close()
    app.state.redis_pool.disconnect()
    logger.info("agent_service_stopping")


app = FastAPI(
    title="BeliefCraft Agent Service",
    description="ReAct agent for warehouse decision support",
    version=settings.SERVICE_VERSION,
    docs_url=f"{settings.API_V1_PREFIX}/docs",
    openapi_url=f"{settings.API_V1_PREFIX}/openapi.json",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure properly for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _generate_request_id() -> str:
    """Generate unique request ID"""
    return str(uuid.uuid4())


def _calculate_duration_ms(start_time: float) -> float:
    """Calculate request duration in milliseconds"""
    return round((time.time() - start_time) * 1000, 2)


def _log_request_completion(method: str, path: str, status_code: int, duration_ms: float) -> None:
    """Log request completion with details"""
    logger.info(
        "request_completed",
        method=method,
        path=path,
        status_code=status_code,
        duration_ms=duration_ms,
    )


# Request ID middleware
@app.middleware("http")
async def add_request_id(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Add request ID and timing to all requests"""
    request_id = _generate_request_id()
    request.state.request_id = request_id

    structlog.contextvars.bind_contextvars(request_id=request_id)

    start_time = time.time()
    try:
        response = await call_next(request)
    finally:
        structlog.contextvars.unbind_contextvars("request_id")

    duration_ms = _calculate_duration_ms(start_time)

    _log_request_completion(
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        duration_ms=duration_ms,
    )

    response.headers["X-Request-ID"] = request_id
    return response


# Exception handler
@app.exception_handler(AgentServiceException)
async def agent_exception_handler(request: Request, exc: AgentServiceException) -> JSONResponse:
    """Handle custom agent service exceptions"""
    logger.error(
        "agent_error",
        error_type=type(exc).__name__,
        error_message=str(exc),
        request_id=request.state.request_id,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.error_code,
            "message": str(exc),
            "request_id": request.state.request_id,
        },
    )


# Root endpoint
@app.get("/", tags=["root"])
async def root() -> dict[str, str]:
    """Root endpoint with service information"""
    return {
        "service": settings.SERVICE_NAME,
        "version": settings.SERVICE_VERSION,
        "status": "running",
        "docs": f"{settings.API_V1_PREFIX}/docs",
        "health": f"{settings.API_V1_PREFIX}/health",
    }


@app.get("/health", tags=["health"])
async def root_health(request: Request) -> dict[str, object]:
    """Root health endpoint for container orchestration checks"""
    checker = HealthChecker(settings, request.app.state.redis_client, request.app.state.http_client)
    dependencies = await checker.check_all_dependencies()
    overall_status = checker.determine_overall_status(dependencies)
    return {
        "status": overall_status,
        "service": settings.SERVICE_NAME,
        "version": settings.SERVICE_VERSION,
        "dependencies": dependencies,
    }


# Include routers
app.include_router(
    health.router,
    prefix=settings.API_V1_PREFIX,
    tags=["health"],
)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=True,
    )
