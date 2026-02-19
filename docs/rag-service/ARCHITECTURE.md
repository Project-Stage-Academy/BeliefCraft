# RAG Service Architecture

The RAG (Retrieval-Augmented Generation) Service is a FastAPI-based service that exposes a Model Context Protocol (MCP) interface for retrieving knowledge from the 'Algorithms for Decision Making' book.

It is located in the monorepo under `services/rag-service/`.

## High-level responsibilities

- Provide a Model Context Protocol (MCP) interface for agent interaction.
- Perform semantic search across the knowledge base.
- Enable graph-like expansion of search results (retrieving linked formulas, algorithms, etc.).
- Provide precise retrieval of entities by their unique identifiers (e.g., formula numbers).
- Abstract the underlying vector store through a repository pattern.

## Runtime dependencies

- **FastMCP**: Used to implement the MCP server and expose tools.
- **FastAPI**: Used to host the MCP server over HTTP/SSE.
- **Common Package**: Utilizes `common.http_client`, `common.logging`, `common.middleware`, and `common.utils`.

## Code structure

- `src/rag_service/main.py`: Service entry point, FastAPI initialization, and MCP server mounting.
- `src/rag_service/mcp_tools.py`: Definition of MCP tools and the `RagTools` class.
- `src/rag_service/repositories.py`: Abstract repository interface and implementations (e.g., `FakeDataRepository`).
The repository pattern allows for easy swapping of the underlying data store without changing the MCP tool logic.
- `src/rag_service/models.py`: Pydantic models for documents, entities, and filters.
- `src/rag_service/config.py`: Configuration settings and schema.

## MCP Tools

The service exposes the following tools via MCP:

- `search_knowledge_base`: Semantic search with optional graph expansion and metadata filtering.
- `expand_graph_by_ids`: Retrieve linked entities for a set of document IDs.
- `get_entity_by_number`: Precise lookup of entities (formulas, algorithms, etc.) by their unique number.

## Observability

- Structured logging using the common logging utility and middleware.
- Fastmcp middlewares for error handling, timing, and structured logging of tool calls. They are configured in `main.py`.
- Health endpoint at `/health` for service monitoring.
