# Agent Service Deployment

This repo supports running the service either locally (Python) or via Docker Compose.

## Local development

From repo root:

```bash
cd services/agent-service

# If you use uv (recommended by current README)
python -m pip install uv
uv sync

cp .env.example .env
# edit .env

uv run uvicorn app.main:app --reload --port 8003
```

Open:
- `http://localhost:8003/api/v1/docs`

## Docker Compose

From repo root:

```bash
docker-compose up agent-service
```

The service listens on `8003` on the host.

Dependencies:
- `redis`
- `environment-api`
- `rag-service`

## Health checks

Docker healthcheck probes:
- `GET http://localhost:8003/api/v1/health`

If you change `API_V1_PREFIX` or the service port, update the compose healthcheck accordingly.

## Ports

Default port mapping in `docker-compose.yml`:
- host `8003` -> container `8003`
