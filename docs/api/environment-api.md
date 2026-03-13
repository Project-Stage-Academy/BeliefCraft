# Environment API Reference

## Overview
`environment-api` is a FastAPI service that exposes warehouse analytics over PostgreSQL through REST endpoints.

Current implementation includes:
- Health endpoint: `/health`
- Smart-query endpoints under `/api/v1/smart-query`
- Response envelope: `ToolResult` with fields `data`, `message`, `meta`

This service is **not** implemented as an MCP server in the current repository.

## Base URL
- Local: `http://localhost:8000`
- Health: `GET /health`
- API group: `/api/v1/smart-query`

## Endpoint Contract
All smart-query endpoints return:
```json
{
  "data": "...",
  "message": "...",
  "meta": {}
}
```

Validation and errors:
- Invalid query params/domain validation: `422`
- Internal execution failures: `500` with generic message

## Endpoints

### GET `/health`
Example:
```json
{
  "status": "ok",
  "env": "local"
}
```

### GET `/api/v1/smart-query/inventory/current`
Returns current inventory rows sorted by available qty ascending.

Query params:
- `warehouse_id` (optional)
- `location_id` (optional)
- `sku` (optional)
- `product_id` (optional)
- `include_reserved` (default: `true`)
- `limit` (`1..500`, default `50`)
- `offset` (`>=0`, default `0`)

### GET `/api/v1/smart-query/shipments/delay-summary`
Returns aggregate shipment delay KPIs and delayed shipment list.

Query params:
- `date_from` (required datetime)
- `date_to` (required datetime)
- `warehouse_id` (optional)
- `route_id` (optional)
- `status` (optional)

### GET `/api/v1/smart-query/observations/compare-balances`
Compares weighted observed quantities vs inventory balances.

Query params:
- `observed_from` (required datetime)
- `observed_to` (required datetime)
- `warehouse_id` (optional)
- `location_id` (optional)
- `sku` (optional)
- `product_id` (optional)
- `limit` (`1..500`, default `50`)
- `offset` (`>=0`, default `0`)

### GET `/api/v1/smart-query/orders/at-risk`
Returns near-term at-risk orders with penalty exposure and top missing SKUs.

Query params:
- `horizon_hours` (`1..720`, default `48`)
- `min_sla_priority` (`0..1`, default `0.7`)
- `status` (optional)
- `top_missing_skus_limit` (`1..50`, default `5`)
- `limit` (`1..500`, default `50`)
- `offset` (`>=0`, default `0`)

## Data Contracts
Canonical request/response schemas are in:
- `packages/common/src/common/schemas/common.py`
- `packages/common/src/common/schemas/inventory.py`
- `packages/common/src/common/schemas/shipments.py`
- `packages/common/src/common/schemas/observations.py`
- `packages/common/src/common/schemas/orders.py`

## Configuration
- `.env` example: `services/environment-api/.env.example`
- Main DB variable: `DATABASE_URL`
- YAML config root: `services/environment-api/config/default.yaml`
- Optional config override env var: `ENVIRONMENT_API_CONFIG`


## Database data population
It's important to provide --force-wipe flag to ensure that this process fully recreates db.
```cli
uv run python -m environment_api.data_generator.generate_seed_data --force-wipe
```
