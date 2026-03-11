"""
Abstract vector store repository and implementations.
"""

import json
import random
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import weaviate
from weaviate.collections.classes.filters import Filter
from weaviate.collections.classes.grpc import MetadataQuery, QueryReference

from .code_entity_processor import CodeDefinitionProcessor
from .constants import (
    COLLECTION_NAME,
    ENTITY_TYPE_TO_CHUNK_TYPE,
    REFERENCE_TYPE_MAP,
    TRAVERSE_TYPE_TO_REFERENCE_FIELD,
)
from .models import Document, EntityType, MetadataFilter, MetadataFilterOperator, MetadataFilters

if TYPE_CHECKING:
    from .config import Settings


class AbstractVectorStoreRepository(ABC):
    """
    Abstract base class for vector store repositories.
    """

    def __init__(self, settings: "Settings") -> None:
        self._settings = settings

    async def __aenter__(self) -> "AbstractVectorStoreRepository":
        """Optional async context manager entry for resource initialization."""
        return self

    async def __aexit__(  # noqa: B027
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
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
                refs: list[str] = cast(
                    list[str], doc.metadata.get(TRAVERSE_TYPE_TO_REFERENCE_FIELD[field])
                )
                chunk_type_value = ENTITY_TYPE_TO_CHUNK_TYPE.get(field, field)
                filters = MetadataFilters(
                    filters=[
                        MetadataFilter(
                            field="chunk_type",
                            operator=MetadataFilterOperator.EQ,
                            value=chunk_type_value,
                        ),
                        MetadataFilter(
                            field="entity_id", operator=MetadataFilterOperator.IN, value=refs
                        ),
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
            case MetadataFilterOperator.EQ:
                return val == field.value
            case MetadataFilterOperator.IN:
                return val in field.value if isinstance(field.value, list) else val == field.value
        return False

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

    Handles semantic search, graph expansion, and code-definition retrieval
    using Weaviate's native collection and reference capabilities.
    """

    def __init__(self, settings: "Settings") -> None:
        """
        Initialize the Weaviate repository.

        Args:
            settings: Application settings containing Weaviate connection parameters.
        """
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
        self._collection = self._client.collections.get(COLLECTION_NAME)

    async def __aenter__(self) -> "WeaviateRepository":
        """
        Establish connection to Weaviate.

        Returns:
            The connected repository instance.
        """
        if not self._client.is_connected():
            await self._client.connect()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """
        Close the Weaviate connection.

        Args:
            exc_type: Exception type.
            exc_val: Exception value.
            exc_tb: Exception traceback.
        """
        await self._client.close()

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

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
            filters: Optional metadata filters.

        Returns:
            List of documents.
        """
        return await self.search_with_expansion(query, k, filters)

    async def get_by_ids(self, ids: list[str]) -> list[Document]:
        """
        Retrieve documents by their unique identifiers.

        Args:
            ids: List of document UUIDs.

        Returns:
            List of matching documents.
        """
        if not ids:
            return []

        results = await self._query(
            filters=Filter.by_id().contains_any(ids),
            return_references=self._get_return_references(),
        )
        return self._process_results(results.objects)

    async def expand_graph_by_ids(
        self, document_ids: list[str], traverse_types: list[EntityType]
    ) -> list[Document]:
        """
        Retrieve linked documents for specific root documents.

        Args:
            document_ids: List of root document UUIDs.
            traverse_types: Types of linked objects to expand.

        Returns:
            List of expanded linked documents.
        """
        if not document_ids or not traverse_types:
            return []

        reference_fields = [TRAVERSE_TYPE_TO_REFERENCE_FIELD[t] for t in traverse_types]
        results = await self._query(
            filters=Filter.by_id().contains_any(document_ids),
            return_references=self._get_return_references(reference_fields),
        )
        return self._process_results(
            results.objects, expansion_fields=reference_fields, include_root=False
        )

    async def search_with_expansion(
        self,
        query: str,
        k: int,
        filters: MetadataFilters | None = None,
        traverse_types: list[EntityType] | None = None,
    ) -> list[Document]:
        """
        Vector search with optional graph expansion in a single operation.

        Args:
            query: Text query for embedding and similarity search.
            k: Maximum number of root documents to return.
            filters: Optional metadata filters.
            traverse_types: Optional list of linked object types to expand.

        Returns:
            List of root and expanded documents.
        """
        reference_fields = [TRAVERSE_TYPE_TO_REFERENCE_FIELD[t] for t in (traverse_types or [])]
        results = await self._query(
            query_text=query,
            limit=k,
            filters=self._convert_filters(filters),
            return_references=self._get_return_references(reference_fields),
        )
        return self._process_results(results.objects, expansion_fields=reference_fields)

    async def get_related_code_definitions(self, document_ids: list[str]) -> list[Document]:
        """
        Fetch code-definition objects (CodeClass, CodeMethod, CodeFunction)
        linked from the given ``unified_collection`` chunk IDs.

        Args:
            document_ids: UUIDs of ``unified_collection`` chunks.

        Returns:
            Post-order list of Documents covering all reachable code definitions
            (callees before callers).
        """
        results = await self._query(
            filters=Filter.by_id().contains_any(document_ids),
            return_references=self._build_top_level_code_def_refs(),
        )
        return CodeDefinitionProcessor.collect_code_definitions(results.objects)

    @staticmethod
    def restore_code_fragment(documents: list[Document]) -> str:
        """
        Reconstruct a single ordered Python source fragment from code-definition
        documents returned by :meth:`get_related_code_definitions`.
        """
        return CodeDefinitionProcessor.restore_code_fragment(documents)

    # ------------------------------------------------------------------ #
    # QueryReference builders for code definitions                        #
    # ------------------------------------------------------------------ #

    def _build_nested_code_def_refs(self, max_depth: int = 2) -> list[QueryReference]:
        """
        Build recursive QueryReference objects for the three nested
        code-definition cross-reference fields.

        ``initialized_classes`` is always a leaf. ``referenced_methods`` and
        ``referenced_functions`` are expanded up to *max_depth* levels.
        """
        fields = ("initialized_classes", "referenced_methods", "referenced_functions")
        return [
            QueryReference(
                link_on=field,
                return_references=self._sub_refs_for_code_def_field(field, max_depth),
                return_properties=True,
            )
            for field in fields
        ]

    def _sub_refs_for_code_def_field(
        self, field: str, max_depth: int
    ) -> list[QueryReference] | None:
        """Return sub-references for one nested code-def field, or None for leaves."""
        if field == "initialized_classes" or max_depth == 0:
            return None
        sub_refs = self._build_nested_code_def_refs(max_depth - 1)
        if field == "referenced_methods":
            sub_refs.append(QueryReference(link_on="class_ref", return_properties=True))
        return sub_refs

    def _build_top_level_code_def_refs(self) -> list[QueryReference]:
        """
        Build the top-level QueryReference list for fetching unified_collection
        chunks together with all linked code definitions.
        """
        return [
            QueryReference(link_on="referenced_classes", return_properties=True),
            QueryReference(
                link_on="referenced_methods",
                return_properties=True,
                return_references=self._build_nested_code_def_refs()
                + [QueryReference(link_on="class_ref", return_properties=True)],
            ),
            QueryReference(
                link_on="referenced_functions",
                return_properties=True,
                return_references=self._build_nested_code_def_refs(),
            ),
        ]

    # ------------------------------------------------------------------ #
    # QueryReference builders for unified collection                      #
    # ------------------------------------------------------------------ #

    def _get_return_references(
        self, traverse_fields: list[str] | None = None
    ) -> list[QueryReference]:
        """Build QueryReference objects for the unified collection's reference fields."""
        base_references = [QueryReference(link_on=name) for name in REFERENCE_TYPE_MAP]
        return [
            QueryReference(
                link_on=field_name,
                return_references=(
                    base_references if traverse_fields and field_name in traverse_fields else None
                ),
            )
            for field_name in REFERENCE_TYPE_MAP
        ]

    # ------------------------------------------------------------------ #
    # Weaviate query execution and result conversion                      #
    # ------------------------------------------------------------------ #

    async def _query(
        self,
        query_text: str | None = None,
        limit: int | None = None,
        filters: Any | None = None,
        return_references: list[QueryReference] | None = None,
    ) -> Any:
        """Execute a Weaviate fetch or near-text query."""
        if not query_text:
            return await self._collection.query.fetch_objects(
                limit=limit,
                filters=filters,
                return_references=return_references,
            )
        return await self._collection.query.near_text(
            query=query_text,
            limit=limit,
            filters=filters,
            return_references=return_references,
            return_metadata=MetadataQuery(certainty=True),
        )

    def _to_document(self, weaviate_object: Any) -> Document:
        """Convert a Weaviate unified-collection object to a domain Document."""
        properties = dict(weaviate_object.properties or {})
        metadata = {**properties}
        content = metadata.pop("content", "")

        for field_name in REFERENCE_TYPE_MAP:
            if weaviate_object.references and field_name in weaviate_object.references:
                reference_objects = weaviate_object.references.get(field_name).objects
                metadata[field_name] = [
                    ref_obj.properties.get("entity_id")
                    for ref_obj in reference_objects
                    if ref_obj.properties and ref_obj.properties.get("entity_id")
                ]

        certainty = getattr(weaviate_object.metadata, "certainty", None)
        cosine_similarity = 2 * certainty - 1 if certainty is not None else None
        return Document(
            id=str(weaviate_object.uuid),
            content=content,
            cosine_similarity=cosine_similarity,
            metadata=metadata,
        )

    def _convert_filters(self, filters: MetadataFilters | None) -> Any:
        """Convert domain metadata filters to Weaviate-native filters."""
        if not filters or not filters.filters:
            return None

        operator_map = {
            MetadataFilterOperator.EQ: lambda prop, val: prop.equal(val),
            MetadataFilterOperator.IN: lambda prop, val: prop.contains_any(
                val if isinstance(val, list) else [val]
            ),
        }
        condition_map = {"and": Filter.all_of, "or": Filter.any_of}

        weaviate_filters = [
            operator_map[f.operator](Filter.by_property(f.field), f.value) for f in filters.filters
        ]
        return condition_map[filters.condition](weaviate_filters)

    def _process_results(
        self,
        weaviate_objects: list[Any],
        expansion_fields: list[str] | None = None,
        include_root: bool = True,
    ) -> list[Document]:
        """Convert raw Weaviate objects to Documents, optionally expanding references."""
        seen_uuids: set[str] = set()
        documents: list[Document] = []

        for obj in weaviate_objects:
            if include_root and obj.uuid not in seen_uuids:
                documents.append(self._to_document(obj))
                seen_uuids.add(obj.uuid)
            for field_name in expansion_fields or []:
                if obj.references and field_name in obj.references:
                    field = obj.references.get(field_name)
                    for ref_obj in field.objects if field else []:
                        if ref_obj.uuid not in seen_uuids:
                            documents.append(self._to_document(ref_obj))
                            seen_uuids.add(ref_obj.uuid)

        return documents


REPOSITORY_REGISTRY: dict[str, type[AbstractVectorStoreRepository]] = {
    "FakeDataRepository": FakeDataRepository,
    "WeaviateRepository": WeaviateRepository,
}


def create_repository(settings: "Settings") -> AbstractVectorStoreRepository:
    """Factory function to create the appropriate repository based on settings."""
    return REPOSITORY_REGISTRY[settings.repository](settings)


if __name__ == "__main__":
    import asyncio

    from rag_service.config import Settings

    async def _demo() -> None:
        settings = Settings(
            repository="WeaviateRepository",
            weaviate_host="localhost",
            weaviate_port=8080,
            weaviate_grpc_port=50051,
        )
        sample_ids = ["8b607abb-8ad6-5e92-a051-daa5684344c7"]

        async with WeaviateRepository(settings) as repo:
            docs = await repo.get_related_code_definitions(sample_ids)
            print(WeaviateRepository.restore_code_fragment(docs))

    asyncio.run(_demo())
