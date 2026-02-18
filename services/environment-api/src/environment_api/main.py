from fastapi import FastAPI

from .api.smart_query import router as smart_query_router
from .config_load import settings

app = FastAPI()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "env": settings.app.env}


app.include_router(smart_query_router, prefix="/api/v1")
