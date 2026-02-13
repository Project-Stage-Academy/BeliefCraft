import os
from pathlib import Path

from packages.common.common.utils.config_loader import ConfigLoader
from fastapi import FastAPI

from .config_schema import Settings

env = os.getenv("ENV")  # dev/prod/local or None
service_root = Path(__file__).resolve().parents[2]
settings = ConfigLoader(service_root=service_root).load(
    schema=Settings,
    env=env if env in {"dev", "prod"} else None,
    config_env_var="ENVIRONMENT_API_CONFIG",
)

app = FastAPI()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "env": settings.app.env}
