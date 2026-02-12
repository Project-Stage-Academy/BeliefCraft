# Agent Service Configuration

Configuration is loaded via `pydantic-settings` from environment variables and `.env`.

- Source of truth for variables: `services/agent-service/app/config.py`
- Example file: `services/agent-service/.env.example`

## Required for useful operation

These are effectively required for the service to be “fully healthy”:

- `ENVIRONMENT_API_URL` (example: `http://environment-api:8000/api/v1`)
- `RAG_API_URL` (example: `http://rag-service:8001/api/v1`)
- `ANTHROPIC_API_KEY`

Without `ANTHROPIC_API_KEY`, `/api/v1/health` will report `anthropic=missing_key` and overall status will be `degraded`.

## Variables

### Service
- `SERVICE_NAME` (default: `agent-service`)
- `SERVICE_VERSION` (default: `0.1.0`)
- `API_V1_PREFIX` (default: `/api/v1`)
- `HOST` (default: `0.0.0.0`)
- `PORT` (default: `8003`)

### External services
- `ENVIRONMENT_API_URL` (default: `http://localhost:8000/api/v1`)
- `RAG_API_URL` (default: `http://localhost:8001/api/v1`)

Health checker appends `/health` to these base URLs.

### Redis
- `REDIS_URL` (default: `redis://localhost:6379`)
- `CACHE_TTL_SECONDS` (default: `3600`)

### Anthropic (Claude)
- `ANTHROPIC_API_KEY` (default: empty)
- `ANTHROPIC_MODEL` (default: `claude-sonnet-4.5`)
- `ANTHROPIC_TEMPERATURE` (default: `0.0`)
- `ANTHROPIC_MAX_TOKENS` (default: `4000`)

### Agent
- `MAX_ITERATIONS` (default: `10`)
- `TOOL_TIMEOUT_SECONDS` (default: `30`)

### Logging
- `LOG_LEVEL` (default: `INFO`)

Allowed values: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`.

## Docker Compose notes

In `docker-compose.yml`, the `agent-service` container sets:
- `ENVIRONMENT_API_URL=http://environment-api:8000/api/v1`
- `RAG_API_URL=http://rag-service:8001/api/v1`
- `REDIS_URL=redis://redis:6379`

…and reads `ANTHROPIC_API_KEY` from your host environment.
