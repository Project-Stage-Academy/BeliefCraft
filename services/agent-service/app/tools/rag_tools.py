"""
RAG tools for querying knowledge base and retrieving algorithms.

This module provides tools that allow the ReAct agent to:
- Search knowledge base book semantically
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

from typing import Any, cast

from app.clients.rag_client import RAGAPIClient, RAGClientProtocol
from app.core.constants import (
    DEFAULT_TRAVERSE_TYPES,
    KNOWLEDGE_BASE_BOOK_NAME,
    KnowledgeGraphEntityType,
)
from app.tools.base import APIClientTool, ToolMetadata


class SearchKnowledgeBaseTool(APIClientTool):
    """
    Tool to search the knowledge base semantically.

    Performs vector similarity search on knowledge base book
    to find relevant algorithms, formulas, and theoretical concepts for
    warehouse decision problems.

    Use Cases:
    - Finding theoretical foundations for inventory control
    - Retrieving POMDP/MDP algorithms for decision making
    - Getting formulas for risk assessment (CVaR, tail risk)
    - Searching for Bayesian estimation techniques
    """

    def __init__(self, client: RAGClientProtocol | None = None) -> None:
        """Initialize tool with optional client for dependency injection."""
        self._client = client
        super().__init__()

    def get_client(self) -> RAGClientProtocol:
        """Get RAG API client instance."""
        return self._client if self._client is not None else cast(RAGClientProtocol, RAGAPIClient())

    def get_metadata(self) -> ToolMetadata:
        """Return tool metadata with OpenAI function calling schema."""
        return ToolMetadata(
            name="search_knowledge_base",
            description=(
                f"Search the knowledge base '{KNOWLEDGE_BASE_BOOK_NAME}' book "
                "for relevant algorithms, formulas, and concepts. "
                "Use this to find theoretical foundations for warehouse decisions "
                "(inventory control, POMDP, Bayesian estimation, CVaR). "
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
                        "items": {
                            "type": "string",
                            "enum": [
                                KnowledgeGraphEntityType.FORMULA.value,
                                KnowledgeGraphEntityType.TABLE.value,
                                KnowledgeGraphEntityType.FIGURE.value,
                                KnowledgeGraphEntityType.SECTION.value,
                                KnowledgeGraphEntityType.EXAMPLE.value,
                                KnowledgeGraphEntityType.EXERCISE.value,
                                KnowledgeGraphEntityType.ALGORITHM.value,
                                KnowledgeGraphEntityType.APPENDIX.value,
                            ],
                        },
                        "description": (
                            "Optional: Types of linked entities to automatically retrieve. "
                            "Valid values: 'formula', 'table', 'figure', 'section', "
                            "'example', 'exercise', 'algorithm', 'appendix'. "
                            "Default: all types. Use to filter which entity types to include."
                        ),
                        "default": DEFAULT_TRAVERSE_TYPES,
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

        Raises:
            ValueError: If query is missing or parameters are invalid
        """
        self._validate_required_params(["query"], kwargs)

        # Validate query type
        query = kwargs["query"]
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query must be a non-empty string")

        # Validate k parameter
        k = kwargs.get("k", 5)
        if not isinstance(k, int) or k < 1 or k > 20:
            raise ValueError("k must be an integer between 1 and 20")

        # Validate traverse_types parameter
        traverse_types = kwargs.get("traverse_types")
        if traverse_types is not None:
            if not isinstance(traverse_types, list):
                raise ValueError("traverse_types must be a list")
            valid_types = [e.value for e in KnowledgeGraphEntityType]
            invalid_types = [t for t in traverse_types if t not in valid_types]
            if invalid_types:
                raise ValueError(
                    f"Invalid traverse_types: {invalid_types}. " f"Valid values are: {valid_types}"
                )

        # Validate filters parameter
        filters = kwargs.get("filters")
        if filters is not None and not isinstance(filters, dict):
            raise ValueError("filters must be a dictionary")

        async with self.get_client() as client:
            return await client.search_knowledge_base(
                query=query, k=k, traverse_types=traverse_types, filters=filters
            )


class ExpandGraphByIdsTool(APIClientTool):
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

    def __init__(self, client: RAGClientProtocol | None = None) -> None:
        """Initialize tool with optional client for dependency injection."""
        self._client = client
        super().__init__()

    def get_client(self) -> RAGClientProtocol:
        """Get RAG API client instance."""
        return self._client if self._client is not None else cast(RAGClientProtocol, RAGAPIClient())

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
                        "items": {
                            "type": "string",
                            "enum": [
                                KnowledgeGraphEntityType.FORMULA.value,
                                KnowledgeGraphEntityType.TABLE.value,
                                KnowledgeGraphEntityType.FIGURE.value,
                                KnowledgeGraphEntityType.SECTION.value,
                                KnowledgeGraphEntityType.EXAMPLE.value,
                                KnowledgeGraphEntityType.EXERCISE.value,
                                KnowledgeGraphEntityType.ALGORITHM.value,
                                KnowledgeGraphEntityType.APPENDIX.value,
                            ],
                        },
                        "description": (
                            "Optional: Types of entities to retrieve. "
                            "Valid values: 'formula', 'table', 'figure', 'section', "
                            "'example', 'exercise', 'algorithm', 'appendix'. "
                            "Default: all types."
                        ),
                        "default": DEFAULT_TRAVERSE_TYPES,
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

        Raises:
            ValueError: If document_ids is missing or parameters are invalid
        """
        self._validate_required_params(["document_ids"], kwargs)

        # Validate document_ids type and content
        document_ids = kwargs["document_ids"]
        if not isinstance(document_ids, list):
            raise ValueError("document_ids must be a list")
        if not document_ids:
            raise ValueError("document_ids cannot be empty")
        if not all(isinstance(doc_id, str) for doc_id in document_ids):
            raise ValueError("all document_ids must be strings")

        # Validate traverse_types parameter
        traverse_types = kwargs.get("traverse_types")
        if traverse_types is not None:
            if not isinstance(traverse_types, list):
                raise ValueError("traverse_types must be a list")
            valid_types = [e.value for e in KnowledgeGraphEntityType]
            if not all(isinstance(t, str) for t in traverse_types):
                raise ValueError("all traverse_types must be strings")
            invalid_types = [t for t in traverse_types if t not in valid_types]
            if invalid_types:
                raise ValueError(
                    f"Invalid traverse_types: {invalid_types}. " f"Valid values are: {valid_types}"
                )

        async with self.get_client() as client:
            return await client.expand_graph_by_ids(
                document_ids=document_ids, traverse_types=traverse_types
            )


class GetEntityByNumberTool(APIClientTool):
    """
    Tool to retrieve specific numbered entity from the book.

    Directly fetches a specific algorithm, formula, table, or figure by its
    number as it appears in the knowledge base book.

    Use Cases:
    - Retrieving "Algorithm 3.2 - (s,S) Inventory Policy"
    - Getting "Formula 16.4 - Bayesian Belief Update"
    - Fetching "Table 5.1 - Risk Assessment Methods"
    - Accessing specific figures/diagrams
    """

    def __init__(self, client: RAGClientProtocol | None = None) -> None:
        """Initialize tool with optional client for dependency injection."""
        self._client = client
        super().__init__()

    def get_client(self) -> RAGClientProtocol:
        """Get RAG API client instance."""
        return self._client if self._client is not None else cast(RAGClientProtocol, RAGAPIClient())

    def get_metadata(self) -> ToolMetadata:
        """Return tool metadata with OpenAI function calling schema."""
        return ToolMetadata(
            name="get_entity_by_number",
            description=(
                f"Retrieve a specific numbered entity from '{KNOWLEDGE_BASE_BOOK_NAME}' "
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

        Raises:
            ValueError: If entity_type or number is missing or invalid
        """
        self._validate_required_params(["entity_type", "number"], kwargs)

        # Validate entity_type
        entity_type = kwargs["entity_type"]
        valid_types = ["formula", "table", "algorithm", "figure"]
        if entity_type not in valid_types:
            raise ValueError(f"entity_type must be one of {valid_types}, got '{entity_type}'")

        # Validate number
        number = kwargs["number"]
        if not isinstance(number, str) or not number.strip():
            raise ValueError("number must be a non-empty string")

        async with self.get_client() as client:
            return await client.get_entity_by_number(entity_type=entity_type, number=number)
