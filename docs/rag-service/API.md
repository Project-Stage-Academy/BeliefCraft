# RAG Service API

Base URL (local): `http://localhost:8001`

The RAG Service primarily provides a **Model Context Protocol (MCP)** interface for retrieving knowledge from the "Algorithms for Decision Making" book. It also includes a standard health check endpoint.

## HTTP Endpoints

### GET `/health`
Health check that reports service status.

Response:
```json
{
  "status": "ok",
  "service": "rag-service",
  "timestamp": "2026-02-19T10:00:00Z"
}
```

---

## MCP Interface

The RAG Service exposes its tools via MCP over HTTP/SSE at the following endpoint:

`POST /mcp`

Clients should use an MCP client (such as `fastmcp`) to interact with this endpoint. Client example
with TracedHttpClient is provided below after the tool descriptions.

### Available MCP Tools

#### `search_knowledge_base`
**Universal knowledge base search.** Performs semantic vector search across the book's content.

- **Semantic Search**: Uses embeddings to find the most relevant chunks of text based on the `query`.
- **Metadata Filtering**: Can restrict search to specific parts, sections, or pages using the `filters` argument.
- **Graph Expansion**: If `traverse_types` are provided, it automatically fetches linked entities (like formulas or algorithms mentioned in the text) and includes them in the results.

**Arguments:**
- `query` (string, required): Text query for semantic search.
- `k` (integer, optional, default: 5): Number of initial relevant documents to retrieve.
- `traverse_types` (array of `EntityType`, optional): Types of objects for search results expansion via links (e.g., `["formula", "algorithm"]`).
- `filters` (`SearchFilters`, optional): Metadata filters to restrict search scope.

#### `expand_graph_by_ids`
**Retrieve linked objects for specific document IDs.**

This tool is used when an agent has already identified relevant document chunks (e.g., from a previous search) and needs to retrieve specific referenced entities that weren't automatically expanded. It follows the "graph" of references in the metadata to fetch related formulas, tables, or algorithms.

**Arguments:**
- `document_ids` (array of strings, required): List of document IDs to expand from.
- `traverse_types` (array of `EntityType`, required): Types of linked objects to retrieve.

#### `get_entity_by_number`
**Precise retrieval of a unique object by its number.**

The book "Algorithms for Decision Making" uses a strict numbering system. This tool allows direct access to these entities if their number is known (e.g., "Algorithm 3.2" or "Formula 16.4"). It is highly efficient for targeted lookups.

**Arguments:**
- `entity_type` (`EntityType`, required): Type of entity (e.g., `formula`).
- `number` (string, required): Unique number of the object, e.g., "1.2.3".

---

## Client Usage Example

To interact with the RAG Service, you can use a `fastmcp` client. For tracing and consistent HTTP behavior, it is recommended to use the `TracedHttpClient` from the `common` package.

```python
import asyncio
from common.http_client import TracedHttpClient
from fastmcp.client import Client, StreamableHttpTransport


async def interact_with_rag():
    # Use TracedHttpClient for automatic trace propagation and logging
    async with TracedHttpClient("http://localhost:8001/") as traced_client:
        # Configure the MCP transport to use our traced httpx client
        transport = StreamableHttpTransport(
            "http://localhost:8001/mcp",
            httpx_client_factory=lambda *args, **kwargs: traced_client.get_httpx_client(),
        )

        async with Client(transport) as client:
            # 1. List available tools
            tools = await client.list_tools()
            print(f"Available tools: {[t.name for t in tools]}")

            # 2. Search the knowledge base
            search_result = await client.call_tool(
                "search_knowledge_base",
                {"query": "POMDP belief update", "k": 2}
            )
            print(f"Search result: {search_result}")

            # 3. Expand graph by document IDs
            expanded_docs = await client.call_tool(
                "expand_graph_by_ids",
                {"document_ids": ["chunk_0001"], "traverse_types": ["formula", "algorithm"]}
            )
            print(f"Expanded documents: {expanded_docs}")

            # 4. Get a specific entity by number
            formula = await client.call_tool(
                "get_entity_by_number",
                {"entity_type": "formula", "number": "3.1"}
            )
            print(f"Formula: {formula}")


if __name__ == "__main__":
    asyncio.run(interact_with_rag())
```

---

## Data Models

### `EntityType` (Enum)
- `formula`
- `table`
- `algorithm`
- `image`
- `exercise`
- `example`

### `SearchFilters`
- `part`: One of `I`, `II`, `III`, `IV`, `V`, `Appendices`.
- `section`: Section number (e.g., "2").
- `subsection`: Subsection number (e.g., "2.3").
- `subsubsection`: Subsubsection number (e.g., "2.3.1").
- `page_number`: Integer page number.

### `Document`
The response object for search and retrieval tools.
- `id`: Unique identifier for the document chunk.
- `content`: The text content of the document.
- `cosine_similarity`: Similarity score (for search results).
- `metadata`: Dictionary containing metadata (page number, entity IDs, etc.).
