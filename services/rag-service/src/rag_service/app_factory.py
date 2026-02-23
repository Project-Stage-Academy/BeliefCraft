from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from pathlib import Path

from common.logging import configure_logging, get_logger
from common.middleware import setup_logging_middleware
from common.utils.config_loader import ConfigLoader
from dotenv import load_dotenv
from fastapi import FastAPI
from fastmcp.server.middleware.error_handling import ErrorHandlingMiddleware  # type: ignore
from fastmcp.server.middleware.logging import StructuredLoggingMiddleware  # type: ignore
from fastmcp.server.middleware.timing import TimingMiddleware  # type: ignore

from .config import Settings
from .mcp_tools import create_mcp_server
from .repositories import create_repository


def create_app(env: str = "") -> FastAPI:
    load_dotenv()
    settings = ConfigLoader(
        service_root=Path(__file__).resolve().parents[2],
    ).load(
        schema=Settings,
        env=env or os.getenv("ENV"),
    )
    configure_logging("rag-service", settings.logging.level)
    logging.getLogger("fakeredis").setLevel(settings.logging.fakeredis_level)
    logging.getLogger("docket").setLevel(settings.logging.docket_level)
    logging.getLogger("sse_starlette").setLevel(settings.logging.sse_level)
    logger = get_logger(__name__)

    repository = create_repository(settings)
    mcp = create_mcp_server(repository)
    mcp.add_middleware(
        ErrorHandlingMiddleware(
            include_traceback=True,
            transform_errors=True,
            logger=logger,
        )
    )
    mcp.add_middleware(TimingMiddleware(logger=logger))
    mcp.add_middleware(StructuredLoggingMiddleware(logger=logger))
    mcp_app = mcp.http_app(path="/mcp")
    app = FastAPI(title="BeliefCraft RAG Service", version="0.1.0", lifespan=mcp_app.lifespan)
    app.mount("/", mcp_app)
    setup_logging_middleware(app)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {
            "status": "ok",
            "service": "rag-service",
            "timestamp": datetime.now(UTC).isoformat(),
        }

    return app
