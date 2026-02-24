# Production Deployment Guide

## Scope
This repository currently provides Docker-based runtime artifacts (`Dockerfile` per service + `docker-compose.yml`).

There are no checked-in Helm charts or Kubernetes manifests under `infrastructure/` in the current codebase.

## Baseline Production Approach

### 1. Build Immutable Images
Build each service image from its existing Dockerfile and publish to your registry:
- `services/environment-api/Dockerfile`
- `services/rag-service/Dockerfile`
- `services/agent-service/Dockerfile`
- `services/ui/Dockerfile`

### 2. Inject Environment Configuration
Use runtime secret/config management to provide variables from service `.env.example` files.

Critical variables by service:
- `environment-api`: `DATABASE_URL`
- `rag-service`: `QDRANT_URL`, `DATABASE_URL`
- `agent-service`: `ENVIRONMENT_API_URL`, `RAG_API_URL`, `REDIS_URL`, Bedrock variables (`AWS_DEFAULT_REGION`, `BEDROCK_MODEL_ID`, etc.)
- root infra: `POSTGRES_*`, `ENVIRONMENT_DB`, `RAG_DB`, `QDRANT_PORT`, `REDIS_PORT` (if reusing compose style)

### 3. Run DB Migrations Before App Traffic
Apply Alembic migrations before starting API pods/containers:
```bash
uv run --project packages/database alembic -c packages/database/alembic.ini upgrade head
```

### 4. Health Probes
Use existing health endpoints:
- `environment-api`: `/health`
- `rag-service`: `/health`
- `agent-service`: `/api/v1/health`
- `ui`: `/health`

## Operational Notes (Current Implementation)
- `agent-service` health is degraded when dependency checks fail (environment API, rag API, redis, Bedrock config).
- `rag-service` currently exposes only `/health`; search endpoints are not implemented in this service code yet.
- Structured JSON logging and `X-Request-ID` propagation are already present in common middleware/client utilities.

## Security Notes
- Do not commit `.env` with real credentials.
- Restrict network paths so only required services can reach each other.
- Prefer TLS termination at ingress/load balancer and secure internal traffic per platform standards.
