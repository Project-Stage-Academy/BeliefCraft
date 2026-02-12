import os
from fastapi import FastAPI

from common.utils.config_loader import ConfigLoader
from environment_api.config_schema import Settings

env = os.getenv("ENV")  # dev/prod/local або None
settings = ConfigLoader().load(
    service_name="environment-api",
    schema=Settings,
    env=env if env in {"dev", "prod"} else None,
)

app = FastAPI()


@app.get("/health")
def health():
    return {"status": "ok", "env": settings.app.env}
