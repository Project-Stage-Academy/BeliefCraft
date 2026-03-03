import pytest
import requests
import weaviate
from rag_service.config import Settings
from rag_service.constants import (
    COLLECTION_NAME,
    REFERENCE_TYPE_MAP,
)
from rag_service.models import EntityType, MetadataFilter, MetadataFilters
from rag_service.repositories import WeaviateRepository
from requests import HTTPError, Response, get
from testcontainers.core.waiting_utils import wait_container_is_ready
from testcontainers.weaviate import WeaviateContainer
from weaviate.classes.config import Configure, ReferenceProperty

EXAMPLE_UUID = "00000000-0000-0000-0000-000000000005"
OTHER_UUID = "00000000-0000-0000-0000-000000000004"
A1_UUID = "00000000-0000-0000-0000-000000000003"
F1_UUID = "00000000-0000-0000-0000-000000000002"
ROOT_UUID = "00000000-0000-0000-0000-000000000001"


class FixedWeaviateContainer(WeaviateContainer):
    @wait_container_is_ready(ConnectionError, HTTPError, requests.exceptions.ConnectionError)
    def _connect(self) -> None:
        url = f"http://{self.get_http_host()}:{self.get_http_port()}/v1/.well-known/ready"
        response: Response = get(url)
        response.raise_for_status()


@pytest.fixture(scope="module")
async def weaviate_setup():
    """Module-scoped fixture to start Weaviate, load test data and yield client."""
    with FixedWeaviateContainer("semitechnologies/weaviate:1.35.0") as container:
        host = container.get_container_host_ip()
        port = int(container.get_exposed_port(8080))
        grpc_port = int(container.get_exposed_port(50051))

        client = weaviate.use_async_with_local(
            host=host,
            port=port,
            grpc_port=grpc_port,
        )
        await client.connect()

        await client.collections.create(
            name=COLLECTION_NAME,
            vector_config=Configure.Vectors.self_provided(),
            references=[
                ReferenceProperty(name=name, target_collection=COLLECTION_NAME)
                for name in REFERENCE_TYPE_MAP
            ],
        )
        collection = client.collections.get(COLLECTION_NAME)
        await collection.data.insert(
            properties={
                "content": "E=mc^2",
                "chunk_type": "numbered_formula",
                "entity_id": "F1",
                "page": 5,
            },
            uuid=F1_UUID,
            vector=[0.1] * 1536,
        )
        await collection.data.insert(
            properties={
                "content": "QuickSort",
                "chunk_type": "algorithm",
                "entity_id": "A1",
                "page": 10,
            },
            uuid=A1_UUID,
            vector=[0.2] * 1536,
        )
        await collection.data.insert(
            properties={
                "content": "Physics and Sorting",
                "chunk_type": "text",
                "page": 1,
                "section_title": "Intro",
            },
            uuid=ROOT_UUID,
            vector=[0.3] * 1536,
        )
        await collection.data.insert(
            properties={"content": "Unrelated info", "chunk_type": "text", "page": 100},
            uuid=OTHER_UUID,
            vector=[0.4] * 1536,
        )
        await collection.data.insert(
            properties={
                "content": "Example",
                "chunk_type": "example",
                "page": 101,
                "entity_id": "3.1",
            },
            uuid=EXAMPLE_UUID,
            vector=[0.5] * 1536,
        )
        await collection.data.reference_add(
            from_uuid=ROOT_UUID, from_property="referenced_formulas", to=F1_UUID
        )
        await collection.data.reference_add(
            from_uuid=ROOT_UUID, from_property="referenced_algorithms", to=A1_UUID
        )
        await collection.data.reference_add(
            from_uuid=F1_UUID, from_property="referenced_examples", to=EXAMPLE_UUID
        )

        try:
            yield {
                "host": host,
                "port": port,
                "grpc_port": grpc_port,
            }
        finally:
            await client.close()


@pytest.fixture
async def repo(weaviate_setup):
    """Initialize WeaviateRepository with connection details from the container."""
    settings = Settings(
        repository="WeaviateRepository",
        weaviate_host=weaviate_setup["host"],
        weaviate_port=weaviate_setup["port"],
        weaviate_grpc_port=weaviate_setup["grpc_port"],
    )
    async with WeaviateRepository(settings) as repo:
        yield repo


@pytest.mark.asyncio
async def test_weaviate_get_by_id(repo):
    """Verify get_by_ids returns full metadata and resolved entity_id references."""
    docs = await repo.get_by_ids([ROOT_UUID])

    assert len(docs) == 1
    doc = docs[0]
    assert doc.id == ROOT_UUID
    assert doc.content == "Physics and Sorting"
    assert doc.metadata["section_title"] == "Intro"
    assert doc.metadata["page"] == 1
    # References must be resolved to their entity_id
    assert doc.metadata["referenced_formulas"] == ["F1"]
    assert doc.metadata["referenced_algorithms"] == ["A1"]


@pytest.mark.asyncio
async def test_weaviate_get_by_ids(repo):
    """Verify get_by_ids returns multiple documents."""
    docs = await repo.get_by_ids([ROOT_UUID, OTHER_UUID])

    assert len(docs) == 2
    ids = {d.id for d in docs}
    assert ROOT_UUID in ids
    assert OTHER_UUID in ids


@pytest.mark.parametrize("k, expected_count", [(1, 1), (2, 2), (4, 4), (10, 5)])
@pytest.mark.asyncio
async def test_weaviate_vector_search_returns_correct_k(repo, k, expected_count):
    """Verify vector search returns correct k."""

    def near_vector(*args, **kwargs):
        kwargs.pop("query")
        return repo._collection.query.near_vector(*args, near_vector=[0.4] * 1536, **kwargs)

    repo._collection.query.near_text = near_vector

    docs = await repo.vector_search(query="physics", k=k)

    assert len(docs) == expected_count


@pytest.mark.asyncio
async def test_weaviate_vector_search_with_filters(repo):
    """Verify vector search applies metadata filters correctly."""
    filters = MetadataFilters(
        filters=[
            MetadataFilter(field="chunk_type", operator="eq", value="text"),
            MetadataFilter(field="page", operator="eq", value=1),
        ],
        condition="and",
    )

    def near_vector(*args, **kwargs):
        kwargs.pop("query")
        return repo._collection.query.near_vector(*args, near_vector=[0.4] * 1536, **kwargs)

    repo._collection.query.near_text = near_vector

    docs = await repo.vector_search(query="physics", k=5, filters=filters)

    assert len(docs) == 1
    assert docs[0].id == ROOT_UUID
    assert docs[0].content == "Physics and Sorting"
    assert docs[0].metadata["section_title"] == "Intro"
    assert docs[0].metadata["page"] == 1
    assert docs[0].metadata["referenced_formulas"] == ["F1"]
    assert docs[0].metadata["referenced_algorithms"] == ["A1"]


@pytest.mark.asyncio
async def test_weaviate_vector_search_no_query(repo):
    """Verify vector search works as plain filter when query is empty."""
    filters = MetadataFilters(
        filters=[MetadataFilter(field="page", operator="eq", value=1)], condition="and"
    )

    def near_text(*args, **kwargs):
        raise AssertionError("near_text should not be called when query is empty")

    repo._collection.query.near_text = near_text

    docs = await repo.vector_search(query="", k=5, filters=filters)

    assert len(docs) == 1
    assert docs[0].id == ROOT_UUID
    assert docs[0].content == "Physics and Sorting"
    assert "referenced_formulas" in docs[0].metadata
    assert "referenced_algorithms" in docs[0].metadata


@pytest.mark.asyncio
async def test_weaviate_expand_graph_by_ids_expand_formulas(repo):
    """Verify graph expansion retrieves linked documents with full metadata."""
    expanded = await repo.expand_graph_by_ids([ROOT_UUID], [EntityType.FORMULA])

    assert len(expanded) == 1
    assert expanded[0].id == F1_UUID
    assert expanded[0].content == "E=mc^2"
    assert expanded[0].metadata["entity_id"] == "F1"
    assert expanded[0].metadata["chunk_type"] == "numbered_formula"
    assert expanded[0].metadata["referenced_examples"] == ["3.1"]


@pytest.mark.asyncio
async def test_weaviate_expand_graph_by_ids_expand_algorithms(repo):
    """Verify graph expansion retrieves linked algorithm documents."""
    expanded = await repo.expand_graph_by_ids([ROOT_UUID], [EntityType.ALGORITHM])

    assert len(expanded) == 1
    assert expanded[0].id == A1_UUID
    assert expanded[0].content == "QuickSort"
    assert expanded[0].metadata["entity_id"] == "A1"
    assert expanded[0].metadata["chunk_type"] == "algorithm"


@pytest.mark.asyncio
async def test_weaviate_expand_graph_by_ids_expand_multiple_types(repo):
    """Verify graph expansion can retrieve multiple types of linked documents."""
    expanded = await repo.expand_graph_by_ids(
        [ROOT_UUID], [EntityType.FORMULA, EntityType.ALGORITHM]
    )

    assert len(expanded) == 2
    ids = {d.id for d in expanded}
    assert F1_UUID in ids
    assert A1_UUID in ids


@pytest.mark.asyncio
async def test_weaviate_search_with_expansion(repo):
    """Verify optimized search with expansion returns both root and linked docs."""
    results = await repo.search_with_expansion(
        query="",
        k=1,
        filters=MetadataFilters(
            filters=[
                MetadataFilter(field="chunk_type", operator="eq", value="text"),
                MetadataFilter(field="page", operator="eq", value=1),
            ],
            condition="and",
        ),
        traverse_types=[EntityType.FORMULA, EntityType.ALGORITHM],
    )

    # Should find root + f1 + a1
    assert len(results) == 3
    ids = {d.id for d in results}
    assert ROOT_UUID in ids
    assert F1_UUID in ids
    assert A1_UUID in ids

    root_doc = next(d for d in results if d.id == ROOT_UUID)
    assert "F1" in root_doc.metadata["referenced_formulas"]
    assert "A1" in root_doc.metadata["referenced_algorithms"]
