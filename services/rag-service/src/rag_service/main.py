from __future__ import annotations

from datetime import UTC, datetime

from fastapi import FastAPI

app = FastAPI(title="BeliefCraft RAG Service", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "rag-service",
        "timestamp": datetime.now(UTC).isoformat(),
    }
