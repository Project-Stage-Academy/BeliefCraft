# Environment DB Migrations

This document describes how to apply and operate relational schema migrations for `environment-api`.

## Scope

Initial Alembic revision creates 15 core tables grouped by domain:

- Reference/stochasticity: `warehouses`, `suppliers`, `leadtime_models`, `products`, `locations`, `routes`
- State: `inventory_balances`, `orders`, `order_lines`, `purchase_orders`, `po_lines`, `shipments`
- Events/observability: `inventory_moves`, `sensor_devices`, `observations`

Initial revision:
- `packages/database/alembic/versions/0001_initial_schema.py`

## Local workflow

1. Ensure PostgreSQL is reachable and `DATABASE_URL` (or fallback env vars) are set.
2. Apply migrations:

```bash
uv run --project packages/database alembic -c packages/database/alembic.ini upgrade head
```

3. Verify the expected table count:

```sql
SELECT COUNT(*)
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_name IN (
    'warehouses','suppliers','leadtime_models','products','locations','routes',
    'inventory_balances','orders','order_lines','purchase_orders','po_lines','shipments',
    'inventory_moves','sensor_devices','observations'
  );
```

Expected result: `15`.

## CI/CD workflow

Add a migration stage before service startup:

```bash
uv sync
uv run --project packages/database alembic -c packages/database/alembic.ini upgrade head
```

Recommended gate checks:
- Migration step must succeed before deploy continues.
- Optionally run smoke SQL checks for required FKs/indexes.

## Operational rules

- Alembic revisions are immutable after merge.
- Future schema evolution must be implemented via new `alembic/versions` revisions.
- Keep migration PRs reviewed and version-controlled with service code.
