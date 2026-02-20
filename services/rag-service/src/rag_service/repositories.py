"""
Abstract vector store repository and implementations.
"""

import json
import random
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .models import Document, EntityType, MetadataFilter, MetadataFilters

if TYPE_CHECKING:
    from .config import Settings

ENTITY_TYPE_TO_CHUNK_TYPE: dict[EntityType, str] = {
    EntityType.FORMULA: "numbered_formula",
    EntityType.TABLE: "numbered_table",
    EntityType.ALGORITHM: "algorithm",
    EntityType.IMAGE: "captioned_image",
    EntityType.EXERCISE: "exercise",
    EntityType.EXAMPLE: "example",
}

TRAVERSE_TYPE_TO_REFERENCE_FIELD: dict[EntityType, str] = {
    EntityType.FORMULA: "referenced_formulas",
    EntityType.TABLE: "referenced_tables",
    EntityType.ALGORITHM: "referenced_algorithms",
    EntityType.IMAGE: "referenced_figures",
    EntityType.EXERCISE: "referenced_exercises",
    EntityType.EXAMPLE: "referenced_examples",
}


class AbstractVectorStoreRepository(ABC):
    """
    Abstract base class for vector store repositories.
    """

    def __init__(self, settings: "Settings") -> None:
        self._settings = settings

    @abstractmethod
    async def vector_search(
        self,
        query: str,
        k: int,
        filters: MetadataFilters | None = None,
    ) -> list[Document]:
        """
        Perform semantic similarity search.

        Args:
            query: Text query for embedding and similarity search.
            k: Maximum number of documents to return.
            filters: Optional metadata filters to restrict search scope.

        Returns:
            List of documents.
        """
        pass

    @abstractmethod
    async def get_by_ids(self, ids: list[str]) -> list[Document]:
        """
        Retrieve documents by their IDs.

        Args:
            ids: List of document IDs to retrieve.

        Returns:
            List of matching documents.
        """
        pass

    async def expand_graph_by_ids(
        self, document_ids: list[str], traverse_types: list[EntityType]
    ) -> list[Document]:
        """
        Retrieve linked objects for specific document IDs.

        Default implementation fetches documents by IDs and performs additional
        search for each type of linked object. Backends with native graph capabilities
        can override this for better performance.

        Args:
            document_ids: List of document IDs to expand from.
            traverse_types: Types of linked objects to retrieve (e.g., ["formula", "algorithm"]).

        Returns:
            List of linked documents.
        """
        if not document_ids or not traverse_types:
            return []

        docs = await self.get_by_ids(document_ids)
        results = []

        for doc in docs:
            for field in traverse_types:
                refs: list[str] = doc.metadata.get(TRAVERSE_TYPE_TO_REFERENCE_FIELD[field])  # type: ignore[assignment]
                chunk_type_value = ENTITY_TYPE_TO_CHUNK_TYPE.get(field, field)
                filters = MetadataFilters(
                    filters=[
                        MetadataFilter(field="chunk_type", operator="eq", value=chunk_type_value),
                        MetadataFilter(field="entity_id", operator="in", value=refs),
                    ],
                    condition="and",
                )
                results.extend(await self.vector_search("", k=len(refs), filters=filters))
        return results

    async def search_with_expansion(
        self,
        query: str,
        k: int,
        filters: MetadataFilters | None = None,
        traverse_types: list[EntityType] | None = None,
    ) -> list[Document]:
        """
        Vector search with optional graph expansion.

        Default implementation performs a vector search and then calls expand_graph_by_ids if
        traverse_types are specified. Backends with native graph capabilities can override
        this for better performance.

        Args:
            query: Text query for embedding and similarity search.
            k: Maximum number of documents to return from the initial vector search.
            filters: Optional metadata filters to restrict search scope.
            traverse_types: Optional list of linked object types to
                            expand (e.g., ["formula", "algorithm"]).

        Returns:
            List of documents including expanded linked documents.
        """
        results = await self.vector_search(query, k, filters)
        if traverse_types:
            results.extend(
                await self.expand_graph_by_ids([doc.id for doc in results], traverse_types)
            )
        return results


class FakeDataRepository(AbstractVectorStoreRepository):
    """
    Mock repository implementation for development and testing.

    Loads data from mock_vector_store_data.json and simulates vector search
    with random sampling.
    """

    def __init__(self, settings: "Settings", data_path: Path | None = None) -> None:
        super().__init__(settings)
        if data_path is None:
            data_path = Path(__file__).parent / "mock_vector_store_data.json"

        with data_path.open() as f:
            self._data: list[dict[str, Any]] = json.load(f)

        self._by_id: dict[str, dict[str, Any]] = {doc["chunk_id"]: doc for doc in self._data}

    def _to_document(self, raw: dict[str, Any], similarity: float = 1.0) -> Document:
        """Convert raw JSON data to Document model."""
        return Document(
            id=raw["chunk_id"],
            content=raw["content"],
            cosine_similarity=similarity,
            metadata={k: v for k, v in raw.items() if k not in ("chunk_id", "content")},
        )

    @staticmethod
    def _matches_filter(doc: dict[str, Any], field: MetadataFilter) -> bool:
        """Check if document matches a single filter."""
        val = doc.get(field.field)
        match field.operator:
            case "eq":
                return val == field.value
            case "in":
                return val in field.value if isinstance(field.value, list) else val == field.value

    def _matches_filters(self, doc: dict[str, Any], filters: MetadataFilters) -> bool:
        """Check if document matches all/any filters based on condition."""
        results = (self._matches_filter(doc, f) for f in filters.filters)
        return all(results) if filters.condition == "and" else any(results)

    async def vector_search(
        self, query: str, k: int, filters: MetadataFilters | None = None
    ) -> list[Document]:
        """Simulate vector search with filtering and random sampling."""
        candidates = self._data
        if filters:
            candidates = [d for d in candidates if self._matches_filters(d, filters)]

        # Simulate relevance with random sampling
        sampled = random.sample(candidates, min(k, len(candidates)))
        return [
            self._to_document(d, similarity=round(random.uniform(0.7, 1.0), 3))  # noqa: S311
            for d in sampled
        ]

    async def get_by_ids(self, ids: list[str]) -> list[Document]:
        """Retrieve documents by their chunk IDs."""
        results = []
        for doc_id in ids:
            if doc_id in self._by_id:
                results.append(self._to_document(self._by_id[doc_id]))
        return results


REPOSITORY_REGISTRY: dict[str, type[AbstractVectorStoreRepository]] = {
    "FakeDataRepository": FakeDataRepository,
}


def create_repository(settings: "Settings") -> AbstractVectorStoreRepository:
    """
    Factory function to create the appropriate repository based on settings.

    Args:
        settings: Application settings containing repository class name.

    Returns:
        Configured AbstractVectorStoreRepository implementation.
    """
    repo_class_name = settings.repository
    return REPOSITORY_REGISTRY[repo_class_name](settings)
