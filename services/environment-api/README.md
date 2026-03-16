# Environment API

Environment API for BeliefCraft services.

## Smart Query endpoints

Base prefix: `/api/v1/smart-query`

### Procurement module

- `GET /procurement/suppliers`
- `GET /procurement/suppliers/{supplier_id}`
- `GET /procurement/purchase-orders`
- `GET /procurement/purchase-orders/{purchase_order_id}`
- `GET /procurement/po-lines`
- `GET /procurement/pipeline-summary`

### Inventory audit module

- `GET /inventory/moves`
- `GET /inventory/moves/{move_id}`
- `GET /inventory/moves/{move_id}/audit-trace`
- `GET /inventory/adjustments-summary`

### Topology module

- `GET /topology/warehouses`
- `GET /topology/warehouses/{warehouse_id}`
- `GET /topology/locations`
- `GET /topology/locations/{location_id}`
- `GET /topology/warehouses/{warehouse_id}/locations-tree`
- `GET /topology/warehouses/{warehouse_id}/capacity-utilization`

### Device monitoring module

- `GET /devices`
- `GET /devices/{device_id}`
- `GET /devices/health-summary`
- `GET /devices/anomalies`

### Observed inventory module

- `GET /inventory/observed-snapshot`

Each endpoint returns a unified payload:

- `data`: query result
- `message`: human-readable summary
- `meta`: filters and execution metadata
