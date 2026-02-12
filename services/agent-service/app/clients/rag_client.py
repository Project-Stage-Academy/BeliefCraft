"""
HTTP client for RAG Service (knowledge base).

This client provides typed methods for semantic search,
graph traversal, and entity retrieval from the knowledge base.

Example:
    ```python
    async with RAGAPIClient() as client:
        results = await client.search_knowledge_base(
            query="inventory policy",
            k=5
        )
        
        formula = await client.get_entity_by_number(
            entity_type="formula",
            number="3.2"
        )
    ```
"""

from typing import Any

from common.logging import get_logger

from app.clients.base_client import BaseAPIClient
from app.config import get_settings

logger = get_logger(__name__)


class RAGAPIClient(BaseAPIClient):
    """
    Client for RAG Service (knowledge base).
    
    Provides methods for:
    - Semantic search in knowledge base
    - Graph expansion from document IDs
    - Entity retrieval (formulas, algorithms, tables)
    """
    
    def __init__(self) -> None:
        """Initialize RAG API client with config from settings."""
        settings = get_settings()
        super().__init__(
            base_url=settings.RAG_API_URL,
            service_name="rag-api"
        )
    
    async def search_knowledge_base(
        self,
        query: str,
        k: int = 5,
        traverse_types: list[str] | None = None,
        filters: dict[str, Any] | None = None,
        timeout: float | None = None
    ) -> dict[str, Any]:
        """
        Semantic search in knowledge base with optional graph traversal.
        
        Searches for relevant documents/chunks using vector similarity,
        then optionally expands results by traversing graph relationships.
        
        Args:
            query: Natural language search query
            k: Number of results to return (default: 5)
            traverse_types: Optional list of relationship types to traverse
                          (e.g., ["CITES", "REFERENCES", "RELATED_TO"])
            filters: Optional metadata filters (e.g., {"chapter": "3"})
        
        Returns:
            Dictionary with search results and metadata
        
        Example:
            ```python
            # Basic search
            results = await client.search_knowledge_base(
                query="How to calculate inventory policy?"
            )
            
            # Search with graph expansion
            results = await client.search_knowledge_base(
                query="POMDP belief updates",
                k=10,
                traverse_types=["CITES", "REFERENCES"],
                filters={"chapter": "16"}
            )
            ```
        """
        payload = {
            "query": query,
            "k": k,
            "traverse_types": traverse_types or [],
            "filters": filters or {}
        }
        
        return await self.post("/search/semantic", json=payload, timeout=timeout)
    
    async def expand_graph_by_ids(
        self,
        document_ids: list[str],
        traverse_types: list[str] | None = None
    ) -> dict[str, Any]:
        """
        Expand graph from specific document IDs.
        
        Given a set of document IDs, traverses the knowledge graph
        to find related documents (citations, references, etc.).
        
        Args:
            document_ids: List of document/chunk IDs to expand from
            traverse_types: Optional list of relationship types to follow
                          (e.g., ["CITES", "FOLLOWS", "DEFINES"])
        
        Returns:
            Dictionary with expanded documents and relationships
        
        Example:
            ```python
            # Expand from formula to find related algorithms
            expansion = await client.expand_graph_by_ids(
                document_ids=["formula_3_2", "formula_3_3"],
                traverse_types=["USES_IN", "REFERENCED_BY"]
            )
            ```
        """
        payload = {
            "document_ids": document_ids,
            "traverse_types": traverse_types or []
        }
        
        return await self.post("/search/expand-graph", json=payload)
    
    async def get_entity_by_number(
        self,
        entity_type: str,
        number: str
    ) -> dict[str, Any]:
        """
        Get specific entity (formula, algorithm, table) by number.
        
        Retrieves a specific numbered entity from the textbook,
        such as "Algorithm 3.2" or "Formula 16.4".
        
        Args:
            entity_type: Type of entity ("formula", "algorithm", "table", "figure")
            number: Entity number (e.g., "3.2", "16.4")
        
        Returns:
            Dictionary with entity content and metadata
        
        Example:
            ```python
            # Get specific algorithm
            algo = await client.get_entity_by_number(
                entity_type="algorithm",
                number="3.2"
            )
            print(algo["title"])  # "(s,S) Inventory Policy"
            
            # Get formula
            formula = await client.get_entity_by_number(
                entity_type="formula",
                number="16.4"
            )
            ```
        """
        return await self.get(f"/entity/{entity_type}/{number}")

