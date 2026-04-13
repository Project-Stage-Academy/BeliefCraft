# RAG Service API Reference

## Overview
`rag-service` is a FastAPI service exposing:
- `GET /health`
- MCP endpoint at `/mcp` with 5 tools (`search_knowledge_base`, `expand_graph_by_ids`, `get_entity_by_number`, `get_related_code_definitions`, `get_search_tags_catalog`)

Important current-state note:
- RAG access is MCP-based in the running implementation.
- Legacy REST routes like `/search/semantic`, `/search/expand-graph`, `/entity/{entity_type}/{number}` are not implemented in `services/rag-service/src/rag_service/main.py`.

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

### MCP `/mcp`
Use an MCP client (for example `fastmcp`) and call tools:
- `search_knowledge_base`
- `expand_graph_by_ids`
- `get_entity_by_number`
- `get_related_code_definitions`
- `get_search_tags_catalog`

## Configuration
From `services/rag-service/.env.example`:
- `ENV` (selects YAML config profile)

From `services/rag-service/config/default.yaml` (+ optional `config/{ENV}.yaml`):
- `logging.level`
- `logging.fakeredis_level`
- `logging.docket_level`
- `logging.sse_level`
- `repository` (currently `FakeDataRepository`)

## Implementation Scope Today
Implemented:
- Service bootstrap
- Health check
- MCP server/tool registration
- Mock retrieval through `FakeDataRepository` (`mock_vector_store_data.json`)
