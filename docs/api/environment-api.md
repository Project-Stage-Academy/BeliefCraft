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
  "meta": {
    "count": 0,
    "trace_count": 0
  }
}
```

`meta` follows the shared `ToolResultMeta` contract:
- `count`: generic count of primary returned items
- `trace_count`: optional public-trace count; defaults to `count`
- `pagination`: optional `{ "limit": int, "offset": int }` for list endpoints
- additional tool-specific fields such as `filters`, `warehouse_id`, or `observation_count`

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

### GET `/api/v1/smart-query/inventory/moves`
Returns inventory movement records.

Query params:
- `warehouse_id` (optional)
- `product_id` (optional)
- `move_type` (optional)
- `from_ts` (optional datetime)
- `to_ts` (optional datetime)
- `limit` (`1..500`, default `50`)
- `offset` (`>=0`, default `0`)

### GET `/api/v1/smart-query/inventory/moves/{move_id}`
Returns a single inventory move by id.

Path params:
- `move_id`

### GET `/api/v1/smart-query/inventory/moves/{move_id}/audit-trace`
Returns the audit trace for a single inventory move.

Path params:
- `move_id`

### GET `/api/v1/smart-query/inventory/adjustments-summary`
Returns aggregated inventory adjustment data.

Query params:
- `warehouse_id` (optional)
- `product_id` (optional)
- `from_ts` (optional datetime)
- `to_ts` (optional datetime)

### GET `/api/v1/smart-query/inventory/observed-snapshot`
Returns the observed inventory snapshot.

Query params:
- `quality_status_in` (optional CSV list)
- `dev_mode` (default `false`)

### GET `/api/v1/smart-query/devices`
Returns sensor devices.

Query params:
- `warehouse_id` (optional)
- `device_type` (optional)
- `status` (optional)

### GET `/api/v1/smart-query/devices/health-summary`
Returns device health summary metrics.

Query params:
- `warehouse_id` (optional)
- `since_ts` (optional datetime)
- `as_of` (optional datetime)

### GET `/api/v1/smart-query/devices/anomalies`
Returns detected device anomalies.

Query params:
- `warehouse_id` (optional)
- `window` (`1..720`, default `24`)

### GET `/api/v1/smart-query/devices/{device_id}`
Returns a single sensor device by id.

Path params:
- `device_id`

### GET `/api/v1/smart-query/procurement/suppliers`
Returns suppliers.

Query params:
- `region` (optional)
- `reliability_min` (`0.0..1.0`, optional)
- `reliability_max` (`0.0..1.0`, optional)
- `name_like` (optional)
- `limit` (`1..1000`, default `100`)
- `offset` (`>=0`, default `0`)

### GET `/api/v1/smart-query/procurement/suppliers/{supplier_id}`
Returns a single supplier by id.

Path params:
- `supplier_id`

### GET `/api/v1/smart-query/procurement/purchase-orders`
Returns purchase orders.

Query params:
- `supplier_id` (optional)
- `destination_warehouse_id` (optional)
- `status_in` (optional repeated query param)
- `created_after` (optional datetime)
- `created_before` (optional datetime)
- `expected_after` (optional datetime)
- `expected_before` (optional datetime)
- `include_names` (default `false`)
- `limit` (`1..1000`, default `100`)
- `offset` (`>=0`, default `0`)

### GET `/api/v1/smart-query/procurement/purchase-orders/{purchase_order_id}`
Returns a single purchase order by id.

Path params:
- `purchase_order_id`

Query params:
- `include_names` (default `false`)

### GET `/api/v1/smart-query/procurement/po-lines`
Returns purchase order lines.

Query params:
- `purchase_order_id` (optional)
- `purchase_order_ids` (optional repeated query param)
- `product_id` (optional)
- `include_product_fields` (default `false`)

### GET `/api/v1/smart-query/procurement/pipeline-summary`
Returns procurement pipeline summary data.

Query params:
- `destination_warehouse_id` (optional)
- `supplier_id` (optional)
- `status_in` (optional repeated query param)
- `horizon_days` (`1..365`, optional)
- `group_by` (default `warehouse_supplier`)
- `include_names` (default `false`)

### GET `/api/v1/smart-query/topology/warehouses`
Returns warehouses.

Query params:
- `region` (optional)
- `name_like` (optional)
- `limit` (`1..500`, default `50`)
- `offset` (`>=0`, default `0`)

### GET `/api/v1/smart-query/topology/warehouses/{warehouse_id}`
Returns a single warehouse by id.

Path params:
- `warehouse_id`

### GET `/api/v1/smart-query/topology/locations`
Returns locations.

Query params:
- `warehouse_id` (optional)
- `type` (optional)
- `parent_location_id` (optional)
- `code_like` (optional)
- `limit` (`1..500`, default `50`)
- `offset` (`>=0`, default `0`)

### GET `/api/v1/smart-query/topology/locations/{location_id}`
Returns a single location by id.

Path params:
- `location_id`

### GET `/api/v1/smart-query/topology/warehouses/{warehouse_id}/locations-tree`
Returns the warehouse location tree.

Path params:
- `warehouse_id`

### GET `/api/v1/smart-query/topology/warehouses/{warehouse_id}/capacity-utilization`
Returns capacity utilization for a warehouse snapshot.

Path params:
- `warehouse_id`

Query params:
- `snapshot_at` (optional datetime)
- `observed_from` (optional datetime)
- `observed_to` (optional datetime)
- `lookback_hours` (`1..720`, default `24`)
- `type` (optional)

## Data Contracts
Canonical request/response schemas are in:
- `packages/common/src/common/schemas/common.py`
- `packages/common/src/common/schemas/devices.py`
- `packages/common/src/common/schemas/inventory.py`
- `packages/common/src/common/schemas/observed_inventory.py`
- `packages/common/src/common/schemas/procurement.py`
- `packages/common/src/common/schemas/topology.py`

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
