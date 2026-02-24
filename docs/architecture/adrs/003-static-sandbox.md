# ADR-003: Use of a Static Data Sandbox for MVP

## Status
Accepted

## Date
2026-02-23

## Context
Early-stage agent development needs deterministic behavior for reproducible tests, stable debugging, and safe experimentation.

The repository already includes:
- deterministic schema + migrations (`packages/database`, Alembic)
- synthetic data generation (`services/environment-api/src/environment_api/data_generator`)
- read-oriented smart-query endpoints in `environment-api`

## Decision
Use a controlled sandbox dataset in PostgreSQL for MVP development and validation.

`environment-api` reads from this dataset to support consistent evaluation of ReAct tool usage.

## Consequences

### Positive
- Deterministic test scenarios and easier regression analysis.
- Safe development without direct coupling to live WMS/ERP systems.
- Faster local iteration for agent prompts and tool schemas.

### Negative
- Lower realism versus live operational systems.
- Requires periodic reseeding/recalibration to keep scenarios representative.
- Production integration work still needed later.

## Alternatives Considered
- Direct live integration in MVP: rejected due to safety and high integration cost.
- Ad-hoc mocks only: rejected because cross-table consistency is harder than using real relational seed data.
