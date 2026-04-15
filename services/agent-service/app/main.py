import os
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

import redis
import structlog
from app.api.v1.routes import agent, health, tools
from app.config_load import settings
from app.core.constants import HEALTH_CHECK_TIMEOUT
from app.core.exceptions import AgentServiceError
from app.core.logging import configure_logging
from common.http_client import TracedHttpClient
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

logger = configure_logging()


async def _close_resource_safely(resource: Any, *, event: str, message: str) -> None:
    """Attempt async resource cleanup without interrupting service shutdown/startup fallback."""
    try:
        await resource.close()
    except Exception as e:
        logger.warning(
            event,
            error=str(e),
            error_type=type(e).__name__,
            message=message,
        )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    from app.clients.rag_mcp_client import RAGMCPClient
    from app.tools import ToolRegistryFactory
    from app.tools.registration import (
        register_mcp_rag_tools,
        register_skill_tools,
    )

    # Startup
    logger.info("agent_service_starting", version=settings.app.version)

    # Configure LangSmith tracing
    if settings.langsmith.tracing_v2 and settings.langsmith.api_key:
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGCHAIN_API_KEY"] = settings.langsmith.api_key
        if settings.langsmith.project:
            os.environ["LANGCHAIN_PROJECT"] = settings.langsmith.project
        logger.info(
            "langsmith_tracing_enabled",
            project=settings.langsmith.project,
        )
    else:
        logger.info("langsmith_tracing_disabled")

    from app.services.health_checker import verify_aws_credentials_at_startup

    verify_aws_credentials_at_startup(settings)

    # Create persistent HTTP client
    http_client = TracedHttpClient("", timeout=HEALTH_CHECK_TIMEOUT)
    await http_client.__aenter__()
    app.state.http_client = http_client

    # Create Redis connection pool
    app.state.redis_pool = redis.ConnectionPool.from_url(settings.redis.url, decode_responses=True)
    app.state.redis_client = redis.Redis(connection_pool=app.state.redis_pool)

    # Build EnvSubAgent registry (environment tools only)
    logger.info("building_env_sub_agent_registry")
    env_sub_registry = ToolRegistryFactory.create_env_sub_agent_registry()
    app.state.env_sub_agent_registry = env_sub_registry
    logger.info(
        "env_sub_agent_registry_built",
        tools_count=len(env_sub_registry.tools),
    )

    # Create persistent MCP client
    mcp_client = RAGMCPClient(base_url=settings.external_services.rag_api_url)
    mcp_rag_tools = []
    try:
        await mcp_client.connect()
        app.state.rag_mcp_client = mcp_client

        logger.info(
            "loading_mcp_rag_tools",
            rag_mcp_url=f"{settings.external_services.rag_api_url}/mcp",
        )

        # Create temporary registry for MCP tool discovery
        temp_registry = ToolRegistryFactory.create_rag_sub_agent_registry()
        await register_mcp_rag_tools(mcp_client, registry=temp_registry)

        # Extract loaded MCP tools for reuse
        mcp_rag_tools = [
            t for t in temp_registry.tools.values() if t.get_metadata().category == "rag"
        ]

        logger.info("mcp_rag_tools_loaded_successfully", count=len(mcp_rag_tools))

    except Exception as e:
        logger.warning(
            "failed_to_load_mcp_tools_continuing_without_rag",
            error=str(e),
            error_type=type(e).__name__,
            message="Service will continue with skill tools only",
        )
        await _close_resource_safely(
            mcp_client,
            event="failed_to_cleanup_mcp_client_after_startup_error",
            message="MCP cleanup failed after startup error, continuing without RAG tools",
        )

    # Register skill tools and get store
    skill_tools = []
    logger.info("loading_skill_tools", skills_dir=settings.app.skills_dir)
    try:
        temp_registry = ToolRegistryFactory.create_react_agent_registry()
        register_skill_tools(settings.app.skills_dir, registry=temp_registry)
        skill_tools = [
            t for t in temp_registry.tools.values() if t.get_metadata().category == "skill"
        ]
        logger.info("skill_tools_loaded_successfully", count=len(skill_tools))
    except Exception as e:
        logger.warning(
            "failed_to_load_skill_tools_continuing_without_skills",
            error=str(e),
            error_type=type(e).__name__,
            skills_dir=settings.app.skills_dir,
            message="Service will continue with RAG tools only",
        )

    # Build RAG sub-agent registry
    logger.info("building_rag_sub_agent_registry")
    rag_sub_registry = ToolRegistryFactory.create_rag_sub_agent_registry(
        mcp_rag_tools=mcp_rag_tools
    )
    app.state.rag_sub_agent_registry = rag_sub_registry
    logger.info(
        "rag_sub_agent_registry_built",
        tools_count=len(rag_sub_registry.tools),
    )

    # Build ReActAgent registry (skill tools + sub-agent orchestrators)
    logger.info("building_react_agent_registry")
    react_registry = ToolRegistryFactory.create_react_agent_registry(
        skill_tools=skill_tools,
        env_sub_registry=env_sub_registry,
        rag_sub_registry=rag_sub_registry,
    )
    app.state.react_agent_registry = react_registry
    logger.info(
        "react_agent_registry_built",
        tools_count=len(react_registry.tools),
        skill_tools=len(skill_tools),
        has_env_orchestrator=bool(env_sub_registry),
        has_rag_orchestrator=bool(rag_sub_registry),
    )

    try:
        yield
    finally:
        logger.info("agent_service_stopping")

        if hasattr(app.state, "rag_mcp_client"):
            await _close_resource_safely(
                app.state.rag_mcp_client,
                event="failed_to_close_rag_mcp_client_on_shutdown",
                message="RAG MCP client cleanup failed during shutdown",
            )

        app.state.redis_client.close()
        app.state.redis_pool.disconnect()
        await http_client.__aexit__(None, None, None)


app = FastAPI(
    title="BeliefCraft Agent Service",
    description="ReAct agent for warehouse decision support",
    version=settings.app.version,
    docs_url=f"{settings.app.api_v1_prefix}/docs",
    openapi_url=f"{settings.app.api_v1_prefix}/openapi.json",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.app.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _generate_request_id() -> str:
    return str(uuid.uuid4())


def _calculate_duration_ms(start_time: float) -> float:
    return round((time.time() - start_time) * 1000, 2)


def _log_request_completion(method: str, path: str, status_code: int, duration_ms: float) -> None:
    logger.info(
        "request_completed",
        method=method,
        path=path,
        status_code=status_code,
        duration_ms=duration_ms,
    )


@app.middleware("http")
async def add_request_id(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
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


@app.exception_handler(AgentServiceError)
async def agent_exception_handler(request: Request, exc: AgentServiceError) -> JSONResponse:
    logger.error(
        "agent_error",
        error_type=type(exc).__name__,
        error_message=str(exc),
        request_id=request.state.request_id,
        exc_info=True,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.error_code,
            "message": str(exc),
            "request_id": request.state.request_id,
        },
    )


@app.get("/", tags=["root"])
async def root() -> dict[str, str]:
    return {
        "service": settings.app.name,
        "version": settings.app.version,
        "status": "running",
        "docs": f"{settings.app.api_v1_prefix}/docs",
        "health": f"{settings.app.api_v1_prefix}/health",
    }


app.include_router(health.router, prefix=settings.app.api_v1_prefix, tags=["health"])
app.include_router(agent.router, prefix=settings.app.api_v1_prefix, tags=["agent"])
app.include_router(tools.router, prefix=settings.app.api_v1_prefix, tags=["tools"])

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.server.host,
        port=settings.server.port,
        reload=True,
    )
