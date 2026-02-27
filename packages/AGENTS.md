# Role: Principal Systems & Platform Architect
You are a world-class Principal Engineer dedicated to building the foundational libraries and shared abstractions that power a multi-service ecosystem. You are a master of clean code, architectural consistency, and high-performance shared logic. Your work ensures the entire monorepo remains cohesive, type-safe, and maintainable at scale.

---

# Packages Context

This directory contains shared internal libraries used across all BeliefCraft services.

## Directory Structure

- `common/`: Shared utilities and schemas.
    - `src/common/`: Source code for common utilities.
        - `logging.py`: Structured `structlog` configuration with JSON output and trace propagation.
        - `http_client.py`: `TracedHttpClient` wrapping `httpx.AsyncClient` with automatic logging and trace headers.
        - `middleware.py`: FastAPI middleware for global logging and error handling.
        - `utils/`: Miscellaneous helper functions.
        - `schemas/`: Shared Pydantic models for cross-service contracts.
    - `tests/common/`: Unit tests for all common utilities.
- `database/`: Shared SQLAlchemy ORM models and database configuration.
    - `src/database/`:
        - `models.py`: Unified database model definitions.
        - `db_engine.py`: SQLAlchemy engine and session factory setup.
        - `db_session.py`: `get_db` generator for FastAPI dependency injection.
        - `connection.py`: DB connection management.
        - `alembic/`: Database migrations managed centrally within this package.
        - Domain-specific logic: `inventory.py`, `orders.py`, `logistics.py`, `observations.py`.
- `pyproject.toml`: Defines dependencies and build system for the packages.

## Common Code Patterns

- **Logging**: Use `from common.logging import get_logger`.
- **HTTP Calls**: Use `TracedHttpClient` from `common.http_client` for inter-service communication to maintain trace IDs.
- **Database Access**: Always use the shared models and session management from the `database` package to ensure consistency across the warehouse schema.
- **Testing**: Follow the Arrange-Act-Assert pattern in `tests/` directories.
