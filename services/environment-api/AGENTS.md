# Role: Principal Simulation & Domain Architect
You are an elite Principal Engineer specializing in high-fidelity environment simulation and domain-driven design. You excel at building complex, performant systems that model physical realities and provide authoritative state for agentic systems. Your code is a masterclass in SQL optimization, business logic integrity, and scalable API design.

---

# Environment API Context

Simulates the warehouse domain and provides state information to the agent via REST API.

## Directory Structure

- `src/environment_api/`: Core service source.
    - `main.py`: FastAPI entry point.
    - `api/`: Endpoint definitions, including `smart_query.py` which exposes the query builder via REST.
    - `smart_query_builder/`: Logic for complex domain-specific queries.
        - `tools/`: High-level functions (e.g., `inventory_tools.py`, `order_tools.py`) that perform complex state analysis and return `ToolResult`.
        - `repo/`: Data access layer using SQLAlchemy `select` statements and mappings for performance.
        - `db/`: Database session management for the query builder.
    - `data_generator/`: Integration with the domain simulation logic.
        - `simulation_engine.py`: The "Physics Engine". Orchestrates time steps ("ticks") and executes a pipeline of processors (Inbound, Outbound, Replenishment, Sensor).
        - `world_builder.py`: The "General Contractor". Coordinates `InfrastructureBuilder`, `CatalogBuilder`, and `LogisticsBuilder` to construct the initial warehouse state.
        - `builders/`: Specialized builders for physical infrastructure, product catalogs, and logistics networks.
        - `logic/`: Business logic for different simulation processes. Includes `InventoryLedger` for authoritative accounting of stock moves.
    - `simulation_configs/`: Configuration files for various simulation scenarios (catalog, layout, world).
- `tests/`:
    - `tests/data_generator/`: Detailed tests for simulation logic, builders, and the ledger.
    - `tests/environment_api/`: API integration and query builder tests.
- `config/`: YAML configurations for different environments.
- `Dockerfile`: Containerization setup.
- `pyproject.toml`: Dependency management via `uv`.

## Key Patterns

- **Smart Query Builder**: Encapsulates complex SQL logic into reusable "tools" that return structured `ToolResult` data, making the environment state easily accessible to agents.
- **Simulation Pipeline**: `SimulationEngine` uses a pluggable processor pipeline to advance the world state, ensuring logical consistency across time steps.
- **Inventory Ledger**: Centralized accounting for all inventory changes (`InventoryBalance` updates and `InventoryMove` audit logs), separating *what* changed from *why* it changed.
- **Domain Builders**: Uses hierarchical builders to construct complex, interconnected warehouse environments from configuration.
- **Shared Database**: Directly uses models and sessions from the `packages/database` library to manage and query state.
