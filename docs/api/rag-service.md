# RAG Service API Reference

## Overview
`rag-service` is currently a minimal FastAPI service with a health endpoint.

Important current-state note:
- The repository contains an agent-side RAG client/tool contract (`/search/semantic`, `/search/expand-graph`, `/entity/{entity_type}/{number}`),
- but these endpoints are **not implemented** in `services/rag-service/src/rag_service/main.py` yet.

## Base URL
- Local: `http://localhost:8001`

## Endpoints

### GET `/health`
Example response:
```json
{
  "status": "ok",
  "service": "rag-service",
  "timestamp": "2026-02-23T21:00:00+00:00"
}
```

## Configuration
From `services/rag-service/.env.example`:
- `PORT`
- `LOG_LEVEL`
- `RAG_INDEX_PATH`
- `DATABASE_URL`
- `QDRANT_URL`

## Implementation Scope Today
Implemented:
- Service bootstrap
- Health check

Not implemented in this service code yet:
- Semantic search HTTP API
- Graph expansion HTTP API
- Entity-by-number HTTP API
- Ingestion/vectorization runtime endpoints
