## BeliefCraft Database Models

SQLAlchemy ORM models for the warehouse schema. This package is intended to be used by
services, data generators, and notebooks that need type-safe access to the DB.

## Requirements

- Python 3.11
- `uv`

## Install

```bash
cd packages/database
uv sync
```

## Configuration

Preferred:
- `DATABASE_URL` (works for local or deployed DB)

Fallback (if `DATABASE_URL` is not set):
- `SUPABASE_USER`
- `SUPABASE_PASSWORD`
- `SUPABASE_HOST`
- `SUPABASE_PORT`
- `SUPABASE_DB`

Optional:
- `DB_SSLMODE` (overrides SSL mode, e.g. `require`, `disable`)

## Basic Usage

```python
from sqlalchemy.orm import Session

from packages.database.src.connection import get_engine
from packages.database.src.models import Product

engine = get_engine()

with Session(engine) as session:
    products = session.query(Product).limit(5).all()
    print(products)
```

## Schema Conformance Tests

Read-only tests that compare ORM metadata to a local Postgres schema.

```bash
TEST_DATABASE_URL="postgresql://postgres:localpass@localhost:5432/bc_test" \
  uv --project packages/database run pytest -q tests/test_orm_schema_conformance.py
```

These tests skip automatically if `TEST_DATABASE_URL` is not set or if it points to Supabase.