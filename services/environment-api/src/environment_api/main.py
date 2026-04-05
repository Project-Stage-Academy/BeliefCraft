from fastapi import FastAPI

from .api.form_options import router as form_options_router
from .api.smart_query import router as smart_query_router
from .config_load import settings

app = FastAPI(
    title="Environment API",
    description="API contract for the Environment service.",
    version="1.0.0",
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "env": settings.app.env}


app.include_router(smart_query_router, prefix="/api/v1")
app.include_router(form_options_router, prefix="/api/v1")
