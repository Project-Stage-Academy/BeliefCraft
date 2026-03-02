# Database Schema Documentation

## Overview
BeliefCraft uses PostgreSQL as the relational source of truth for warehouse simulation and analytics. The canonical schema is defined by:
- ORM models in `packages/database/src/database/*.py`
- initial migration `packages/database/src/database/alembic/versions/0001_initial_schema.py`

The initial schema contains **15 core tables**.

## Tables by Domain

### Logistics and Reference
- `warehouses`: `id`, `name`, `region`, `tz`
- `suppliers`: `id`, `name`, `reliability_score`, `region`
- `leadtime_models`: `id`, `scope`, `dist_family`, `p1`, `p2`, `p_rare_delay`, `rare_delay_add_days`, `fitted_at`
- `routes`: `id`, `origin_warehouse_id`, `destination_warehouse_id`, `mode`, `distance_km`, `leadtime_model_id`
- `shipments`: `id`, `direction`, `origin_warehouse_id`, `destination_warehouse_id`, `order_id`, `purchase_order_id`, `route_id`, `status`, `shipped_at`, `arrived_at`

### Inventory
- `products`: `id`, `sku`, `name`, `category`, `shelf_life_days`
- `locations`: `id`, `warehouse_id`, `parent_location_id`, `code`, `type`, `capacity_units`
- `inventory_balances`: `id`, `product_id`, `location_id`, `on_hand`, `reserved`, `last_count_at`, `quality_status`
- `inventory_moves`: `id`, `product_id`, `from_location_id`, `to_location_id`, `move_type`, `qty`, `occurred_at`, `reason_code`, `reported_qty`, `actual_qty`

### Orders and Procurement
- `orders`: `id`, `customer_name`, `status`, `promised_at`, `sla_priority`, `requested_ship_from_region`, `created_at`
- `order_lines`: `id`, `order_id`, `product_id`, `qty_ordered`, `qty_allocated`, `qty_shipped`, `service_level_penalty`
- `purchase_orders`: `id`, `supplier_id`, `destination_warehouse_id`, `status`, `expected_at`, `leadtime_model_id`, `created_at`
- `po_lines`: `id`, `purchase_order_id`, `product_id`, `qty_ordered`, `qty_received`

### Observability
- `sensor_devices`: `id`, `warehouse_id`, `device_type`, `noise_sigma`, `missing_rate`, `bias`, `status`
- `observations`: `id`, `observed_at`, `device_id`, `product_id`, `location_id`, `obs_type`, `observed_qty`, `confidence`, `is_missing`, `reported_noise_sigma`, `related_move_id`, `related_shipment_id`

## ENUM Types
Defined in `packages/database/src/database/enums.py`:

- `quality_status`: `ok`, `damaged`, `expired`, `quarantine`
- `move_type`: `inbound`, `outbound`, `transfer`, `adjustment`
- `location_type`: `shelf`, `bin`, `pallet_pos`, `dock`, `virtual`
- `order_status`: `new`, `allocated`, `picked`, `shipped`, `cancelled`
- `po_status`: `draft`, `submitted`, `partial`, `received`, `closed`
- `device_type`: `camera`, `rfid_reader`, `weight_sensor`, `scanner`
- `device_status`: `active`, `offline`, `maintenance`
- `shipment_status`: `planned`, `in_transit`, `delivered`, `exception`
- `shipment_direction`: `inbound`, `outbound`, `transfer`
- `route_mode`: `truck`, `air`, `rail`, `sea`
- `leadtime_scope`: `supplier`, `route`, `global`
- `dist_family`: `normal`, `lognormal`, `poisson`
- `obs_type`: `scan`, `image_recog`, `manual_count`

## Migrations
Apply migrations from repo root:
```bash
uv run --project packages/database alembic -c packages/database/alembic.ini upgrade head
```

SQL bootstrap script used by docker migration container:
- `infrastructure/scripts/postgres/migrations/001_initial_schema.sql`
