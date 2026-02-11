# Agent Service API

Base URL (local): `http://localhost:8003`

Interactive docs:
- Swagger UI: `/api/v1/docs`
- OpenAPI JSON: `/api/v1/openapi.json`

## Conventions

### Request ID
All HTTP responses include `X-Request-ID` header.

### Errors
Custom service errors (raised as `AgentServiceException`) are returned as JSON:

```json
{
  "error": "INTERNAL_ERROR",
  "message": "Human readable message",
  "request_id": "<uuid>"
}
```

Note: FastAPI/Pydantic validation errors for request schemas are returned in FastAPI’s default format unless explicitly wrapped.

## Endpoints

### GET `/`
Returns basic service information.

Response:
```json
{
  "service": "agent-service",
  "version": "0.1.0",
  "status": "running",
  "docs": "/api/v1/docs",
  "health": "/api/v1/health"
}
```

### GET `/api/v1/health`
Health check that reports dependency connectivity/configuration.

Response:
```json
{
  "status": "healthy | degraded",
  "service": "agent-service",
  "version": "0.1.0",
  "timestamp": "2026-02-11T12:34:56.789+00:00",
  "dependencies": {
    "environment_api": "healthy | unhealthy | error: ...",
    "rag_api": "healthy | unhealthy | error: ...",
    "redis": "healthy | error: ...",
    "anthropic": "configured | missing_key"
  }
}
```

Dependency status values used by the implementation:
- `healthy`, `unhealthy`, `degraded`, `configured`, `missing_key`
- error statuses are prefixed with `error: `

### Planned (not wired yet)
These route modules exist but are not currently included in the FastAPI app router:
- `app/api/v1/routes/agent.py`
- `app/api/v1/routes/tools.py`

When they are implemented and included, document them here.
