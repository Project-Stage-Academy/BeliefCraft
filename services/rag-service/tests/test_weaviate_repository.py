import inspect

import pytest
import requests
import weaviate
from rag_service.config import Settings
from rag_service.constants import (
    ALGORITHM_REF_FIELD,
    CLASS_REF_FIELD,
    CODE_CLASS_COLLECTION,
    CODE_FUNCTION_COLLECTION,
    CODE_METHOD_COLLECTION,
    COLLECTION_NAME,
    REFERENCE_TYPE_MAP,
    CodeEntityRef,
)
from rag_service.models import Document, EntityType, MetadataFilter, MetadataFilters
from rag_service.repositories import WeaviateRepository
from requests import HTTPError, Response, get
from testcontainers.core.waiting_utils import wait_container_is_ready
from testcontainers.weaviate import WeaviateContainer
from weaviate.classes.config import Configure, ReferenceProperty
from weaviate.collections.classes.config import VectorDistances

EXAMPLE_UUID = "00000000-0000-0000-0000-000000000005"
OTHER_UUID = "00000000-0000-0000-0000-000000000004"
A1_UUID = "00000000-0000-0000-0000-000000000003"
F1_UUID = "00000000-0000-0000-0000-000000000002"
ROOT_UUID = "00000000-0000-0000-0000-000000000001"

CODE_CLASS_UUID = "00000000-0000-0000-0000-000000000006"
CODE_METHOD_UUID = "00000000-0000-0000-0000-000000000007"
CODE_CALLER_UUID = "00000000-0000-0000-0000-000000000008"
CODE_CALLEE_UUID = "00000000-0000-0000-0000-000000000009"
CODE_UNRELATED_UUID = "00000000-0000-0000-0000-000000000010"


class FixedWeaviateContainer(WeaviateContainer):
    @wait_container_is_ready(ConnectionError, HTTPError, requests.exceptions.ConnectionError)
    def _connect(self) -> None:
        url = f"http://{self.get_http_host()}:{self.get_http_port()}/v1/.well-known/ready"
        response: Response = get(url, timeout=5)
        response.raise_for_status()


def _vector_config():
    return Configure.Vectors.self_provided(
        vector_index_config=Configure.VectorIndex.flat(distance_metric=VectorDistances.COSINE)
    )


async def _add_reference_if_missing(collection, name: str, target: str) -> None:
    config = await collection.config.get()
    if any(ref.name == name for ref in config.references):
        return
    maybe_awaitable = collection.config.add_reference(
        ReferenceProperty(name=name, target_collection=target)
    )
    if inspect.isawaitable(maybe_awaitable):
        await maybe_awaitable


async def _create_collections(client):
    await client.collections.create(
        name=CODE_CLASS_COLLECTION,
        vector_config=_vector_config(),
        references=[],
    )
    await client.collections.create(
        name=CODE_FUNCTION_COLLECTION,
        vector_config=_vector_config(),
        references=[],
    )
    await client.collections.create(
        name=CODE_METHOD_COLLECTION,
        vector_config=_vector_config(),
        references=[
            ReferenceProperty(name=CLASS_REF_FIELD, target_collection=CODE_CLASS_COLLECTION),
        ],
    )
    await client.collections.create(
        name=COLLECTION_NAME,
        vector_config=_vector_config(),
        references=[
            ReferenceProperty(name=name, target_collection=COLLECTION_NAME)
            for name in REFERENCE_TYPE_MAP
        ],
    )

    return (
        client.collections.get(COLLECTION_NAME),
        client.collections.get(CODE_CLASS_COLLECTION),
        client.collections.get(CODE_METHOD_COLLECTION),
        client.collections.get(CODE_FUNCTION_COLLECTION),
    )


async def _configure_cross_collection_refs(collection, code_classes, code_methods, code_functions):
    await _add_reference_if_missing(
        collection, CodeEntityRef.REFERENCED_CLASSES, CODE_CLASS_COLLECTION
    )
    await _add_reference_if_missing(
        collection, CodeEntityRef.REFERENCED_METHODS, CODE_METHOD_COLLECTION
    )
    await _add_reference_if_missing(
        collection, CodeEntityRef.REFERENCED_FUNCTIONS, CODE_FUNCTION_COLLECTION
    )

    for code_collection in (code_classes, code_methods, code_functions):
        await _add_reference_if_missing(
            code_collection, CodeEntityRef.REFERENCED_CLASSES, CODE_CLASS_COLLECTION
        )
        await _add_reference_if_missing(
            code_collection, CodeEntityRef.REFERENCED_METHODS, CODE_METHOD_COLLECTION
        )
        await _add_reference_if_missing(
            code_collection, CodeEntityRef.REFERENCED_FUNCTIONS, CODE_FUNCTION_COLLECTION
        )
        await _add_reference_if_missing(code_collection, ALGORITHM_REF_FIELD, COLLECTION_NAME)


async def _seed_chunk_documents(collection):
    await collection.data.insert(
        properties={
            "content": "E=mc^2",
            "chunk_type": "numbered_formula",
            "entity_id": "F1",
            "page": 5,
        },
        uuid=F1_UUID,
        vector=[0.1] * 2,
    )
    await collection.data.insert(
        properties={
            "content": "QuickSort",
            "chunk_type": "algorithm",
            "entity_id": "A1",
            "page": 10,
        },
        uuid=A1_UUID,
        vector=[0.2] * 2,
    )
    await collection.data.insert(
        properties={
            "content": "Physics and Sorting",
            "chunk_type": "text",
            "page": 1,
            "section_title": "Intro",
        },
        uuid=ROOT_UUID,
        vector=[0.3] * 2,
    )
    await collection.data.insert(
        properties={"content": "Unrelated info", "chunk_type": "text", "page": 100},
        uuid=OTHER_UUID,
        vector=[0.4] * 2,
    )
    await collection.data.insert(
        properties={
            "content": "Example",
            "chunk_type": "example",
            "page": 101,
            "entity_id": "3.1",
        },
        uuid=EXAMPLE_UUID,
        vector=[0.5] * 2,
    )


async def _seed_code_documents(code_classes, code_methods, code_functions):
    await code_classes.data.insert(
        properties={
            "name": "Runner",
            "content": "class Runner:\n    def __init__(self):\n        self.enabled = True",
        },
        uuid=CODE_CLASS_UUID,
        vector=[0.11] * 2,
    )
    await code_methods.data.insert(
        properties={
            "name": "run",
            "content": "def run(self):\n    return execute()",
        },
        uuid=CODE_METHOD_UUID,
        vector=[0.12] * 2,
    )
    await code_functions.data.insert(
        properties={
            "name": "execute",
            "content": "def execute():\n    return helper()",
        },
        uuid=CODE_CALLER_UUID,
        vector=[0.13] * 2,
    )
    await code_functions.data.insert(
        properties={
            "name": "helper",
            "content": "def helper():\n    return 1",
        },
        uuid=CODE_CALLEE_UUID,
        vector=[0.14] * 2,
    )
    await code_functions.data.insert(
        properties={
            "name": "unrelated",
            "content": "def unrelated():\n    return -1",
        },
        uuid=CODE_UNRELATED_UUID,
        vector=[0.15] * 2,
    )


async def _seed_references(collection, code_methods, code_functions):
    await collection.data.reference_add(
        from_uuid=ROOT_UUID, from_property="referenced_formulas", to=F1_UUID
    )
    await collection.data.reference_add(
        from_uuid=ROOT_UUID, from_property="referenced_algorithms", to=A1_UUID
    )
    await collection.data.reference_add(
        from_uuid=F1_UUID, from_property="referenced_examples", to=EXAMPLE_UUID
    )

    await collection.data.reference_add(
        from_uuid=ROOT_UUID,
        from_property=CodeEntityRef.REFERENCED_METHODS,
        to=CODE_METHOD_UUID,
    )
    await collection.data.reference_add(
        from_uuid=ROOT_UUID,
        from_property=CodeEntityRef.REFERENCED_FUNCTIONS,
        to=CODE_CALLER_UUID,
    )

    await code_methods.data.reference_add(
        from_uuid=CODE_METHOD_UUID,
        from_property=CLASS_REF_FIELD,
        to=CODE_CLASS_UUID,
    )
    await code_methods.data.reference_add(
        from_uuid=CODE_METHOD_UUID,
        from_property=CodeEntityRef.REFERENCED_FUNCTIONS,
        to=CODE_CALLER_UUID,
    )

    await code_functions.data.reference_add(
        from_uuid=CODE_CALLER_UUID,
        from_property=CodeEntityRef.REFERENCED_FUNCTIONS,
        to=CODE_CALLEE_UUID,
    )


@pytest.fixture(scope="module")
async def weaviate_setup():
    """Module-scoped fixture to start Weaviate, load test data and yield client."""
    with FixedWeaviateContainer("semitechnologies/weaviate:1.35.0") as container:
        host = container.get_container_host_ip()
        port = int(container.get_exposed_port(8080))
        grpc_port = int(container.get_exposed_port(50051))

        client = weaviate.use_async_with_local(host=host, port=port, grpc_port=grpc_port)
        await client.connect()

        try:
            collection, code_classes, code_methods, code_functions = await _create_collections(
                client
            )
            await _configure_cross_collection_refs(
                collection, code_classes, code_methods, code_functions
            )
            await _seed_chunk_documents(collection)
            await _seed_code_documents(code_classes, code_methods, code_functions)
            await _seed_references(collection, code_methods, code_functions)

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
    assert "referenced_examples" not in doc.metadata


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
        return repo._collection.query.near_vector(*args, near_vector=[0.4] * 2, **kwargs)

    repo._collection.query.near_text = near_vector

    docs = await repo.vector_search(query="physics", k=k)

    assert len(docs) == expected_count
    for doc in docs:
        assert doc.cosine_similarity is not None


@pytest.mark.parametrize(
    "filters",
    [
        MetadataFilters(
            filters=[
                MetadataFilter(field="page", operator="in", value=[4, 6]),
                MetadataFilter(field="page", operator="in", value=[1, 2, 3]),
            ],
            condition="or",
        ),
        MetadataFilters(
            filters=[MetadataFilter(field="page", operator="in", value=[1, 2, 3])], condition="and"
        ),
        MetadataFilters(
            filters=[
                MetadataFilter(field="chunk_type", operator="eq", value="text"),
                MetadataFilter(field="page", operator="eq", value=1),
            ],
            condition="and",
        ),
    ],
)
@pytest.mark.asyncio
async def test_weaviate_vector_search_with_filters(repo, filters):
    """Verify vector search applies metadata filters correctly."""

    def near_vector(*args, **kwargs):
        kwargs.pop("query")
        return repo._collection.query.near_vector(*args, near_vector=[0.3, 0.4], **kwargs)

    repo._collection.query.near_text = near_vector

    docs = await repo.vector_search(query="physics", k=5, filters=filters)

    assert len(docs) == 1
    assert docs[0].id == ROOT_UUID
    assert docs[0].content == "Physics and Sorting"
    assert docs[0].metadata["section_title"] == "Intro"
    assert docs[0].metadata["page"] == 1
    assert docs[0].metadata["referenced_formulas"] == ["F1"]
    assert docs[0].metadata["referenced_algorithms"] == ["A1"]
    assert "referenced_examples" not in docs[0].metadata
    assert round(docs[0].cosine_similarity, 4) == round(0.989949, 4)


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
    assert "referenced_examples" not in docs[0].metadata


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
    assert "referenced_algorithms" not in expanded[0].metadata


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
    assert "referenced_examples" not in root_doc.metadata


@pytest.mark.asyncio
async def test_weaviate_get_related_code_definitions(repo):
    """Verify code-definition graph traversal returns one wrapped content document."""
    repo._build_nested_code_def_refs = (  # type: ignore[method-assign]
        lambda max_depth=10: WeaviateRepository._build_nested_code_def_refs(repo, min(max_depth, 1))
    )

    result = await repo.get_related_code_definitions([ROOT_UUID])

    assert isinstance(result, Document)
    assert result.id is None
    assert result.metadata is None
    assert result.cosine_similarity is None

    assert "def helper():" in result.content
    assert "def execute():" in result.content
    assert "class Runner:" in result.content
    assert "def run(self):" in result.content

    # Dependencies should appear before their callers in reconstructed source.
    assert result.content.index("def helper():") < result.content.index("def execute():")

    # Caller is referenced from both root and method, but should only appear once.
    assert result.content.count("def execute():") == 1

    # Unrelated function should never be pulled into the fragment.
    assert "def unrelated():" not in result.content
