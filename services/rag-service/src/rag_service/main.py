import logging
import os
from pathlib import Path

from common.logging import configure_logging, get_logger
from common.middleware import setup_logging_middleware
from common.utils.config_loader import ConfigLoader
from dotenv import load_dotenv
from fastapi import FastAPI

from .config import Settings
from .mcp_tools import create_mcp_server

load_dotenv()
settings = ConfigLoader(
    service_root=Path(__file__).resolve().parents[2],
).load(
    schema=Settings,
    env=os.getenv("ENV"),
)
configure_logging("rag-service", settings.logging.level)
logging.getLogger("fakeredis").setLevel(settings.logging.fakeredis_level)
logging.getLogger("docket").setLevel(settings.logging.docket_level)
logging.getLogger("sse_starlette").setLevel(settings.logging.sse_level)
logger = get_logger(__name__)

mcp = create_mcp_server()
mcp_app = mcp.http_app(path="/mcp")
app = FastAPI(title="RAG API", lifespan=mcp_app.lifespan)
app.mount("/", mcp_app)
setup_logging_middleware(app)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
