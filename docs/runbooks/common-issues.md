# Common Issues and Resolutions

## 1. Missing `.env` Files
### Symptom
`docker compose up` fails or services start with missing environment errors.

### Resolution
Create env files from examples:
```bash
cp .env.example .env
cp services/environment-api/.env.example services/environment-api/.env
cp services/rag-service/.env.example services/rag-service/.env
cp services/agent-service/.env.example services/agent-service/.env
cp services/ui/.env.example services/ui/.env
```

## 2. PostgreSQL Ready but Smart Queries Return Errors/Empty Data
### Symptom
`environment-api` smart-query endpoints fail (`500`/relation errors) or return empty payloads on a fresh local stack.

### Likely Cause
Environment simulation tables/data were not initialized yet.

### Resolution
```bash
cd services/environment-api
uv run python -m environment_api.data_generator.generate_seed_data
```

Then restart the API:
```bash
docker compose restart environment-api
```

If startup still fails, inspect migration/bootstrap logs:
```bash
docker compose logs db-migrate --tail=200
docker compose logs postgres --tail=200
```

## 3. `agent-service` Health Is `degraded`
### Symptom
`GET /api/v1/health` shows non-healthy dependency statuses.

### Resolution
Check each dependency:
- `environment_api`: verify `ENVIRONMENT_API_URL` and `/health`
- `rag_api`: verify `RAG_API_URL` and `/health`
- `redis`: verify Redis container is healthy
- `aws_bedrock`: ensure Bedrock settings are present (`AWS_DEFAULT_REGION`, `BEDROCK_MODEL_ID`)

Useful commands:
```bash
curl -s http://localhost:8003/api/v1/health | jq .
docker compose logs agent-service --tail=200
```

## 4. `422 Unprocessable Entity` from Environment Smart Queries
### Symptom
Requests to `/api/v1/smart-query/*` fail with validation errors.

### Likely Cause
Invalid parameter ranges/types (e.g. bad date range, `limit > 500`, invalid datetime format).

### Resolution
Validate against endpoint contracts in `docs-new/api/environment-api.md`.

## 5. Agent Query Fails with Bedrock Errors
### Symptom
`POST /api/v1/agent/analyze` returns `500` and logs show Bedrock/auth errors.

### Likely Cause
Missing/incorrect AWS credentials or region/model configuration.

### Resolution
Check `services/agent-service/.env`:
- `AWS_DEFAULT_REGION`
- `BEDROCK_MODEL_ID`
- credentials (`AWS_PROFILE` or access key/secret)

Then restart:
```bash
docker compose restart agent-service
```

## 6. Expecting RAG Search Endpoints but Getting 404
### Symptom
Calls to `/search/semantic` on `rag-service` return `404`.

### Cause
Current `rag-service` implementation exposes only `/health`.

### Resolution
Treat search/graph/entity routes as not implemented in this service yet. Keep dependency checks limited to `/health`.

## 7. Agent Tool Calls Fail with 404 on Environment Routes
### Symptom
`POST /api/v1/agent/analyze` fails during tool execution with endpoint-not-found errors from `environment-api`.

### Cause
Current `agent-service` environment client contract uses routes like:
- `/observations/current`
- `/orders/backlog`
- `/shipments/in-transit`
- `/analysis/*`
- `/inventory/history/{product_id}`

Current `environment-api` implementation exposes smart-query routes under:
- `/api/v1/smart-query/*`

### Resolution
Align one side with the other:
1. Update `agent-service` clients/tools to call `/api/v1/smart-query/*`, or
2. Add compatibility routes to `environment-api`.

## 8. Hot Reload Not Reflecting Code Changes
### Symptom
File edits do not appear in running service behavior.

### Resolution
1. Confirm stack started with `make dev` (bind mounts enabled).
2. Check mounted paths inside container.
3. If still stale, recreate containers:
```bash
make clean
make dev
```
