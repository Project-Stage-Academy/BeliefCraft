# ADR-002: Selection of PostgreSQL and Qdrant for Data Storage

## Status
Accepted

## Date
2026-02-23

## Context
BeliefCraft has two storage concerns:
1. Structured transactional warehouse data (orders, inventory, shipments, observations).
2. Vector-oriented retrieval infrastructure for RAG workflows.

The repository already provisions both PostgreSQL and Qdrant in `docker-compose.yml`.

## Decision
Adopt polyglot persistence:
1. PostgreSQL as the system of record for structured warehouse data.
2. Qdrant as vector-store infrastructure for RAG capabilities.

## Consequences

### Positive
- PostgreSQL provides strong relational integrity and SQL analytics.
- Qdrant isolates vector-search workloads from transactional DB workloads.
- Clear separation between operational data and retrieval index concerns.

### Negative
- Additional operational overhead (backup/monitoring for two stores).
- Cross-store consistency must be handled at application level.
- Current `rag-service` implementation is still minimal and does not yet expose search APIs; Qdrant is provisioned but not fully used by runtime endpoints.

## Alternatives Considered
- PostgreSQL + `pgvector` only: lower ops overhead, but less isolation for vector workloads.
- Single document DB: rejected due to strongly relational warehouse model and existing ORM/migration design.
