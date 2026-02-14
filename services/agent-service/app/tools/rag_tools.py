"""
RAG tools for querying knowledge base and retrieving algorithms.

This module provides tools that allow the ReAct agent to:
- Search 'Algorithms for Decision Making' book semantically
- Expand knowledge graph from document IDs
- Retrieve specific entities (formulas, algorithms, tables) by number

All tools use RAGAPIClient to communicate with the RAG Service
with automatic retry logic and error handling.

Example:
    ```python
    from app.tools.rag_tools import SearchKnowledgeBaseTool
    from app.tools.registry import tool_registry

    # Register tool
    tool = SearchKnowledgeBaseTool()
    tool_registry.register(tool)

    # Execute tool
    result = await tool_registry.execute_tool(
        "search_knowledge_base",
        {"query": "inventory control POMDP", "k": 5}
    )
    ```
"""

from typing import Any

from app.clients.rag_client import RAGAPIClient
from app.tools.base import BaseTool, ToolMetadata


class SearchKnowledgeBaseTool(BaseTool):
    """
    Tool to search the knowledge base semantically.

    Performs vector similarity search on 'Algorithms for Decision Making' book
    to find relevant algorithms, formulas, and theoretical concepts for
    warehouse decision problems.

    Use Cases:
    - Finding theoretical foundations for inventory control
    - Retrieving POMDP/MDP algorithms for decision making
    - Getting formulas for risk assessment (CVaR, tail risk)
    - Searching for Bayesian estimation techniques
    """

    def get_metadata(self) -> ToolMetadata:
        """Return tool metadata with OpenAI function calling schema."""
        return ToolMetadata(
            name="search_knowledge_base",
            description=(
                "Search 'Algorithms for Decision Making' book for relevant algorithms, "
                "formulas, and concepts. Use this to find theoretical foundations "
                "for warehouse decisions (inventory control, POMDP, Bayesian estimation, CVaR). "
                "Returns semantically similar text chunks from the book."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "Natural language search query. "
                            "Examples: 'inventory control under uncertainty', "
                            "'POMDP belief state update', 'CVaR risk assessment', "
                            "'Bayesian parameter estimation'"
                        ),
                    },
                    "k": {
                        "type": "integer",
                        "description": "Number of results to return (default: 5, max: 20)",
                        "minimum": 1,
                        "maximum": 20,
                        "default": 5,
                    },
                    "traverse_types": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Optional: Types of linked entities to automatically retrieve. "
                            "Examples: ['formula', 'algorithm_code'] will fetch "
                            "all formulas and code referenced by matched text."
                        ),
                    },
                    "filters": {
                        "type": "object",
                        "description": (
                            "Optional: Metadata filters. "
                            "Properties: chapter (string), section (string), "
                            "page_number (integer)"
                        ),
                        "properties": {
                            "chapter": {"type": "string"},
                            "section": {"type": "string"},
                            "page_number": {"type": "integer"},
                        },
                    },
                },
                "required": ["query"],
            },
            category="rag",
        )

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        """
        Execute semantic search in knowledge base.

        Args:
            **kwargs: Must include query (str), optional k (int),
                     traverse_types (list[str]), filters (dict)

        Returns:
            Dictionary with search results and metadata from RAG API
        """
        query = kwargs["query"]
        k = kwargs.get("k", 5)
        traverse_types = kwargs.get("traverse_types")
        filters = kwargs.get("filters")

        async with RAGAPIClient() as client:
            result = await client.search_knowledge_base(  # type: ignore[attr-defined]
                query=query, k=k, traverse_types=traverse_types, filters=filters
            )
        return result  # type: ignore[no-any-return]


class ExpandGraphByIdsTool(BaseTool):
    """
    Tool to expand knowledge graph from specific document IDs.

    Given document IDs from search results, traverses the knowledge graph
    to retrieve related entities (formulas, algorithms, citations, references).
    Useful for getting complete context after initial search.

    Use Cases:
    - Getting formulas referenced by found text
    - Retrieving algorithm code mentioned in explanations
    - Finding related tables and figures
    - Expanding citations and references
    """

    def get_metadata(self) -> ToolMetadata:
        """Return tool metadata with OpenAI function calling schema."""
        return ToolMetadata(
            name="expand_graph_by_ids",
            description=(
                "Retrieve linked entities (formulas, algorithms, tables, citations) "
                "from specific document IDs. Use this after search_knowledge_base "
                "when you've found relevant text and need complete context "
                "(referenced math formulas, algorithm code, related concepts)."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "document_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "List of document/chunk IDs to expand from. "
                            "Get these from search_knowledge_base results."
                        ),
                    },
                    "traverse_types": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Optional: Types of entities to retrieve. "
                            "Examples: ['formula', 'algorithm_code', 'table', 'image']"
                        ),
                    },
                },
                "required": ["document_ids"],
            },
            category="rag",
        )

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        """
        Execute graph expansion from document IDs.

        Args:
            **kwargs: Must include document_ids (list[str]),
                     optional traverse_types (list[str])

        Returns:
            Dictionary with expanded entities and relationships from RAG API
        """
        document_ids = kwargs["document_ids"]
        traverse_types = kwargs.get("traverse_types")

        async with RAGAPIClient() as client:
            result = await client.expand_graph_by_ids(  # type: ignore[attr-defined]
                document_ids=document_ids, traverse_types=traverse_types
            )
        return result  # type: ignore[no-any-return]


class GetEntityByNumberTool(BaseTool):
    """
    Tool to retrieve specific numbered entity from the book.

    Directly fetches a specific algorithm, formula, table, or figure by its
    number as it appears in 'Algorithms for Decision Making'.

    Use Cases:
    - Retrieving "Algorithm 3.2 - (s,S) Inventory Policy"
    - Getting "Formula 16.4 - Bayesian Belief Update"
    - Fetching "Table 5.1 - Risk Assessment Methods"
    - Accessing specific figures/diagrams
    """

    def get_metadata(self) -> ToolMetadata:
        """Return tool metadata with OpenAI function calling schema."""
        return ToolMetadata(
            name="get_entity_by_number",
            description=(
                "Retrieve a specific numbered entity from 'Algorithms for Decision Making' "
                "by its exact number. Use this when you know the specific entity you need "
                "(e.g., Algorithm 3.2, Formula 16.4, Table 5.1). "
                "This is faster than semantic search for known entities."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "entity_type": {
                        "type": "string",
                        "enum": ["formula", "table", "algorithm", "figure"],
                        "description": (
                            "Type of entity to retrieve. "
                            "Options: 'formula', 'table', 'algorithm', 'figure'"
                        ),
                    },
                    "number": {
                        "type": "string",
                        "description": (
                            "Entity number as it appears in the book. "
                            "Examples: '3.2', '16.4', '5.1', '12.3a'"
                        ),
                    },
                },
                "required": ["entity_type", "number"],
            },
            category="rag",
        )

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        """
        Execute entity retrieval by number.

        Args:
            **kwargs: Must include entity_type (str) and number (str)

        Returns:
            Dictionary with entity content and metadata from RAG API
        """
        entity_type = kwargs["entity_type"]
        number = kwargs["number"]

        async with RAGAPIClient() as client:
            result = await client.get_entity_by_number(  # type: ignore[attr-defined]
                entity_type=entity_type, number=number
            )
        return result  # type: ignore[no-any-return]
