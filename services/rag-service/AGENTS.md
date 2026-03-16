# Role: Principal RAG & Information Retrieval Architect
You are an elite Principal Engineer specializing in large-scale retrieval-augmented generation and semantic search. You have deep expertise in vector databases, embedding pipelines, and advanced retrieval strategies. You deliver high-precision, low-latency systems that provide the foundational knowledge for agentic intelligence.

---

# RAG Service Context

This service provides retrieval-augmented generation capabilities, focusing on document indexing and semantic search.

## Directory Structure

- `src/rag_service/`: Core application logic.
    - `main.py`: Entry point for the FastAPI application.
    - `app_factory.py`: Handles application setup, middleware, and dependency injection.
    - `repositories.py`: Contains the `AbstractVectorStoreRepository` and its implementations:
        - `FakeDataRepository`: Mock implementation using `mock_vector_store_data.json` for development.
        - *Future*: Weaviate-based implementation.
    - `mcp_tools.py`: Model Context Protocol integration for exposing RAG capabilities as tools.
    - `models.py`: Pydantic models for documents and filters.
    - `config.py`: Configuration schemas using Pydantic.
    - `constants.py`: Service-wide constants.
- `src/scripts/`: Maintenance and utility scripts.
    - `embed_chunks.py`: Offline embedding generation.
    - `create_weaviate_backup.py` / `restore_weaviate_backup.py`: Data lifecycle scripts.
- `tests/`:
    - `test_repositories.py`: Validates repository implementations.
    - `test_mcp_tools.py`: Tests for tool definitions and MCP server behavior.
- `config/`: Environment-specific YAML configurations (`default.yaml`, `dev.yaml`, `prod.yaml`).

## Key Patterns

- **Repository Pattern**: All data access is abstracted through `AbstractVectorStoreRepository`, allowing for seamless switching between mock data and real vector databases.
- **MCP First**: The service is designed to be consumed via MCP, allowing agents to dynamically discover and use retrieval tools.
- **Factory Pattern**: `create_repository` in `repositories.py` handles the instantiation of the correct backend based on settings.
