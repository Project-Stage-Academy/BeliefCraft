# Runbook: System Debugging and Troubleshooting

## 1. Quick System Check
```bash
docker compose ps
```

Health checks:
```bash
curl -s http://localhost:8000/health
curl -s http://localhost:8001/health
curl -s http://localhost:8003/api/v1/health
curl -s http://localhost:3000/health
```

## 2. Agent Request Debugging
Call analyzer directly:
```bash
curl -s -X POST http://localhost:8003/api/v1/agent/analyze \
  -H 'Content-Type: application/json' \
  -d '{"query":"Which orders are at risk in the next 48 hours?"}'
```

Inspect available tools:
```bash
curl -s http://localhost:8003/api/v1/tools
```

Tail logs:
```bash
docker compose logs -f agent-service
```

## 3. Environment API Query Debugging
Test smart-query endpoints directly:
```bash
curl -G 'http://localhost:8000/api/v1/smart-query/inventory/current' --data-urlencode 'limit=10'
curl -G 'http://localhost:8000/api/v1/smart-query/orders/at-risk' --data-urlencode 'horizon_hours=48'
```

If `agent-service` tool calls return `404`, compare client routes in:
- `services/agent-service/app/clients/environment_client.py`
with implemented `environment-api` routes in:
- `services/environment-api/src/environment_api/api/smart_query.py`

If responses are empty, reseed data:
```bash
cd services/environment-api
uv run python -m environment_api.data_generator.generate_seed_data
```

Note:
- On a fresh local DB, run the seed script before expecting non-empty smart-query results.

## 4. Trace IDs and Correlation
`agent-service` adds `X-Request-ID` to responses. Use it to correlate logs across services where propagated.

## 5. Dependency-Specific Debugging
- Redis: `docker compose logs redis --tail=200`
- PostgreSQL: `docker compose logs postgres --tail=200`
- Migration job: `docker compose logs db-migrate --tail=200`
- RAG service: `docker compose logs rag-service --tail=200`
