# Agent Service Architecture

The Agent Service is a FastAPI service in the monorepo under `services/agent-service/`.

## High-level responsibilities

- Provide an HTTP API for agent-driven workflows (ReAct-style, planned)
- Provide a health endpoint with dependency checks
- Centralize configuration via environment variables and `.env`
- Produce structured JSON logs with a per-request `X-Request-ID`

## Runtime dependencies

- Environment API (configured via `ENVIRONMENT_API_URL`)
- RAG service (configured via `RAG_API_URL`)
- Redis (configured via `REDIS_URL`)
- Anthropic (Claude) configuration (via `ANTHROPIC_API_KEY`)

## Code structure

- `app/main.py`: FastAPI app initialization, middleware, exception handler, router inclusion
- `app/config.py`: `Settings` (`pydantic-settings`) + validation
- `app/api/v1/routes/health.py`: `/api/v1/health`
- `app/services/health_checker.py`: dependency checks (HTTP + Redis + Anthropic config)
- `app/core/`: constants, logging configuration, custom exceptions

## Routing status

Currently included routers:
- Health router only (`/api/v1/health`)

Route stubs exist but are not yet included:
- `app/api/v1/routes/agent.py`
- `app/api/v1/routes/tools.py`

## Observability

- Request middleware binds `request_id` into `structlog` context variables
- Each request logs a `request_completed` event with `method`, `path`, `status_code`, `duration_ms`
