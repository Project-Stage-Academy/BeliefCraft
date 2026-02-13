from fastapi import FastAPI
from .config import settings

app = FastAPI()

@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "env": settings.app.env}
