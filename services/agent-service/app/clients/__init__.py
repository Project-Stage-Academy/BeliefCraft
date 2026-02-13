"""
HTTP clients package for agent service.

This package provides HTTP clients for communicating with external services:
- BaseAPIClient: Foundation with retry logic and observability
- EnvironmentAPIClient: Warehouse and inventory data
- RAGAPIClient: Knowledge base and semantic search

Example:
    ```python
    from app.clients import EnvironmentAPIClient, RAGAPIClient

    async with EnvironmentAPIClient() as env_client:
        obs = await env_client.get_current_observations()

    async with RAGAPIClient() as rag_client:
        results = await rag_client.search_knowledge_base(
            query="inventory policy"
        )
    ```
"""

from app.clients.base_client import BaseAPIClient
from app.clients.environment_client import EnvironmentAPIClient
from app.clients.rag_client import RAGAPIClient

__all__ = [
    "BaseAPIClient",
    "EnvironmentAPIClient",
    "RAGAPIClient",
]
