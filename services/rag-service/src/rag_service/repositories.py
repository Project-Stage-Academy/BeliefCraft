"""
Abstract vector store repository and implementations.
"""

import json
import random
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, Any

import weaviate
from weaviate.collections.classes.filters import Filter
from weaviate.collections.classes.grpc import MetadataQuery, QueryReference

from .constants import (
    COLLECTION_NAME,
    ENTITY_TYPE_TO_CHUNK_TYPE,
    REFERENCE_TYPE_MAP,
    TRAVERSE_TYPE_TO_REFERENCE_FIELD,
)
from .models import Document, EntityType, MetadataFilter, MetadataFilters

if TYPE_CHECKING:
    from .config import Settings


class AbstractVectorStoreRepository(ABC):
    """
    Abstract base class for vector store repositories.
    """

    def __init__(self, settings: "Settings") -> None:
        self._settings = settings

    async def __aenter__(self):
        """Optional async context manager entry for resource initialization."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Optional async context manager exit for resource cleanup."""
        pass

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


class WeaviateRepository(AbstractVectorStoreRepository):
    """
    Weaviate-based vector store repository implementation.
    """

    def __init__(self, settings: "Settings") -> None:
        super().__init__(settings)
        self._client = weaviate.WeaviateAsyncClient(
            connection_params=weaviate.connect.ConnectionParams.from_params(
                http_host=settings.weaviate_host,
                http_port=settings.weaviate_port,
                http_secure=False,
                grpc_host=settings.weaviate_host,
                grpc_port=settings.weaviate_grpc_port,
                grpc_secure=False,
            ),
        )
        # Attribute _collection must exist for test mocks
        self._collection = self._client.collections.get(COLLECTION_NAME)

    async def __aenter__(self):
        """Ensure the Weaviate client is connected."""
        if not self._client.is_connected():
            await self._client.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Close the Weaviate client connection."""
        await self._client.close()

    def _convert_filters(self, filters: MetadataFilters | None) -> Any:
        """Convert repository filters to Weaviate filters."""
        if not filters or not filters.filters:
            return None

        wv_filters = []
        for f in filters.filters:
            if f.operator == "eq":
                wv_filters.append(Filter.by_property(f.field).equal(f.value))
            elif f.operator == "in":
                val = f.value if isinstance(f.value, list) else [f.value]
                wv_filters.append(Filter.by_property(f.field).contains_any(val))

        if not wv_filters:
            return None

        return (
            Filter.all_of(wv_filters) if filters.condition == "and" else Filter.any_of(wv_filters)
        )

    def _get_return_references(
        self, traverse_fields: list[str] | None = None
    ) -> list[QueryReference]:
        """Generate QueryReference list for metadata and expansion."""
        refs = []
        for ref_field in REFERENCE_TYPE_MAP.keys():
            if traverse_fields and ref_field in traverse_fields:
                # When traversing, we want the linked objects to also have their references
                # so that _to_document can resolve them to entity_ids for metadata.
                refs.append(
                    QueryReference(
                        link_on=ref_field,
                        return_references=[
                            QueryReference(link_on=name) for name in REFERENCE_TYPE_MAP
                        ],
                    )
                )
            else:
                refs.append(QueryReference(link_on=ref_field))
        return refs

    def _to_document(self, obj: Any) -> Document:
        """Convert Weaviate object to Document model."""
        metadata = dict(obj.properties) if obj.properties else {}

        # Resolve references to entity_ids in metadata
        for ref_field in REFERENCE_TYPE_MAP.keys():
            if obj.references and ref_field in obj.references:
                metadata[ref_field] = [
                    ref_obj.properties.get("entity_id")
                    for ref_obj in obj.references[ref_field].objects
                    if ref_obj.properties and ref_obj.properties.get("entity_id")
                ]
            elif ref_field not in metadata:
                metadata[ref_field] = []

        distance = (
            obj.metadata.distance if obj.metadata and obj.metadata.distance is not None else 0.0
        )
        return Document(
            id=str(obj.uuid),
            content=metadata.pop("content", ""),
            cosine_similarity=round(1.0 - distance, 3),
            metadata=metadata,
        )

    async def vector_search(
        self,
        query: str,
        k: int,
        filters: MetadataFilters | None = None,
    ) -> list[Document]:
        """Perform semantic similarity search or filtering."""
        wv_filters = self._convert_filters(filters)
        return_refs = self._get_return_references()

        if not query:
            res = await self._collection.query.fetch_objects(
                limit=k, filters=wv_filters, return_references=return_refs
            )
        else:
            res = await self._collection.query.near_text(
                query=query,
                limit=k,
                filters=wv_filters,
                return_references=return_refs,
                return_metadata=MetadataQuery(distance=True),
            )

        return [self._to_document(obj) for obj in res.objects]

    async def get_by_ids(self, ids: list[str]) -> list[Document]:
        """Retrieve documents by their UUIDs."""
        if not ids:
            return []
        res = await self._collection.query.fetch_objects(
            filters=Filter.by_id().contains_any(ids),
            return_references=[QueryReference(link_on=name) for name in REFERENCE_TYPE_MAP],
        )
        return [self._to_document(obj) for obj in res.objects]

    async def expand_graph_by_ids(
        self, document_ids: list[str], traverse_types: list[EntityType]
    ) -> list[Document]:
        """Optimized graph expansion using Weaviate references."""
        if not document_ids or not traverse_types:
            return []

        ref_fields = [TRAVERSE_TYPE_TO_REFERENCE_FIELD[t] for t in traverse_types]
        return_refs = self._get_return_references(ref_fields)

        res = await self._collection.query.fetch_objects(
            filters=Filter.by_id().contains_any(document_ids), return_references=return_refs
        )

        results = []
        seen_ids = set()
        for obj in res.objects:
            if obj.references:
                for ref_field in ref_fields:
                    if ref_field in obj.references:
                        for ref_obj in obj.references[ref_field].objects:
                            if ref_obj.uuid not in seen_ids:
                                results.append(self._to_document(ref_obj))
                                seen_ids.add(ref_obj.uuid)
        return results

    async def search_with_expansion(
        self,
        query: str,
        k: int,
        filters: MetadataFilters | None = None,
        traverse_types: list[EntityType] | None = None,
    ) -> list[Document]:
        """Unified search and expansion in a single optimized operation."""
        wv_filters = self._convert_filters(filters)

        ref_fields = (
            [TRAVERSE_TYPE_TO_REFERENCE_FIELD[t] for t in traverse_types] if traverse_types else []
        )
        return_refs = self._get_return_references(ref_fields)

        if not query:
            res = await self._collection.query.fetch_objects(
                limit=k, filters=wv_filters, return_references=return_refs
            )
        else:
            res = await self._collection.query.near_text(
                query=query,
                limit=k,
                filters=wv_filters,
                return_references=return_refs,
                return_metadata=MetadataQuery(distance=True),
            )

        results = []
        seen_ids = set()
        for obj in res.objects:
            # Add root document
            if obj.uuid not in seen_ids:
                results.append(self._to_document(obj))
                seen_ids.add(obj.uuid)

            # Add linked documents
            if obj.references:
                for ref_field in ref_fields:
                    if ref_field in obj.references:
                        for ref_obj in obj.references[ref_field].objects:
                            if ref_obj.uuid not in seen_ids:
                                results.append(self._to_document(ref_obj))
                                seen_ids.add(ref_obj.uuid)
        return results


REPOSITORY_REGISTRY: dict[str, type[AbstractVectorStoreRepository]] = {
    "FakeDataRepository": FakeDataRepository,
    "WeaviateRepository": WeaviateRepository,
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
