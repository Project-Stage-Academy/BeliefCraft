from unittest.mock import MagicMock, patch

import pytest
import weaviate
from weaviate.collections.classes.config import Configure, ReferenceProperty
from weaviate.collections.classes.data import DataReference
from weaviate.collections.classes.filters import Filter
from weaviate.collections.classes.grpc import QueryReference

from scripts.embed_chunks import (
    COLLECTION_NAME,
    REFERENCE_TYPE_MAP,
    build_reference_map,
    extract_references_from_chunk,
    generate_deterministic_uuid,
    insert_chunks,
    setup_collection,
)


@pytest.mark.parametrize(
    "chunk1, chunk2, expected_equal",
    [
        (
            {"entity_id": "1.2", "chunk_type": "numbered_formula", "content": "c1"},
            {"entity_id": "1.2", "chunk_type": "numbered_formula", "content": "c2", "a": "b"},
            True,
        ),
        (
            {"entity_id": "1.2", "chunk_type": "numbered_formula", "content": "c1"},
            {"entity_id": "1.3", "chunk_type": "numbered_formula", "content": "c2"},
            False,
        ),
        (
            {"entity_id": "1.2", "chunk_type": "numbered_formula", "content": "c1"},
            {"entity_id": "1.2", "chunk_type": "numbered_table", "content": "c2"},
            False,
        ),
        ({"content": "same content", "a": "b"}, {"content": "same content", "a": "b"}, True),
        ({"content": "same content"}, {"content": "different content"}, False),
    ],
)
def test_generate_deterministic_uuid(chunk1, chunk2, expected_equal):
    """Verify UUID generation is stable and follows correct fields."""
    uuid1 = generate_deterministic_uuid(chunk1)
    uuid2 = generate_deterministic_uuid(chunk2)

    if expected_equal:
        assert uuid1 == uuid2
    else:
        assert uuid1 != uuid2


def test_build_reference_map():
    """Verify the reference map correctly indexes chunks by their target entity identity."""
    chunks = [
        {"entity_id": "f1", "chunk_type": "formula", "content": "math"},
        {"entity_id": "a1", "chunk_type": "algorithm", "content": "sort"},
    ]

    ref_map = build_reference_map(chunks)

    assert ("f1", "formula") in ref_map
    assert ("a1", "algorithm") in ref_map
    assert ref_map[("f1", "formula")] == chunks[0]
    assert ref_map[("a1", "algorithm")] == chunks[1]


def test_extract_references_logic():
    """Test the logic of converting reference IDs to UUIDs and cleaning up the chunk dict."""
    target = {"entity_id": "f1", "chunk_type": "numbered_formula", "content": "target"}
    target_uuid = generate_deterministic_uuid(target)
    ref_map = {("f1", "numbered_formula"): target}
    source = {"content": "source", "referenced_formulas": ["f1"], "referenced_algorithms": []}
    source_uuid = generate_deterministic_uuid(source)

    refs = extract_references_from_chunk(source, ref_map)

    assert refs == [
        DataReference(
            from_uuid=source_uuid, from_property="referenced_formulas", to_uuid=target_uuid
        )
    ]
    assert "referenced_formulas" not in source
    assert "referenced_algorithms" not in source


def test_extract_references_missing_target():
    """Verify that references to missing chunks are skipped and a warning is printed."""
    source = {
        "entity_id": "s1",
        "chunk_type": "text",
        "content": "source",
        "referenced_formulas": ["missing_f1"],
    }
    ref_map = {}  # Map is empty, so "missing_f1" won't be found

    with patch("builtins.print") as mock_print:
        refs = extract_references_from_chunk(source, ref_map)

    assert refs == []
    assert "referenced_formulas" not in source
    mock_print.assert_called_with(
        "Warning: Referenced chunk not found with entity_id=missing_f1, "
        "chunk_type=numbered_formula. Skipping reference."
    )


@patch("weaviate.WeaviateClient")
def test_setup_collection_logic(mock_client):
    """Test collection initialization and deletion logic."""
    mock_collections = MagicMock()
    mock_client.collections = mock_collections

    # Case 1: Create if not exists
    mock_collections.exists.return_value = False
    setup_collection(mock_client, recreate=False)
    mock_collections.create.assert_called_once()

    # Case 2: Use existing
    mock_collections.create.reset_mock()
    mock_collections.exists.return_value = True
    setup_collection(mock_client, recreate=False)
    mock_collections.create.assert_not_called()

    # Case 3: Recreate
    mock_collections.create.reset_mock()
    mock_collections.exists.side_effect = [True, False]
    setup_collection(mock_client, recreate=True)
    mock_collections.delete.assert_called_with(COLLECTION_NAME)
    mock_collections.create.assert_called_once()


@pytest.fixture(scope="module")
def weaviate_client():
    client = weaviate.connect_to_embedded()
    client.connect()
    if client.collections.exists(COLLECTION_NAME):
        client.collections.delete(COLLECTION_NAME)
    yield client
    client.close()


@pytest.mark.slow
@pytest.mark.skip
def test_insert_chunks(weaviate_client):
    """Verify chunks can be retrieved after insertion"""
    client = weaviate_client
    client.collections.create(
        name=COLLECTION_NAME,
        vector_config=Configure.Vectors.self_provided(),
        references=[
            ReferenceProperty(name=name, target_collection=COLLECTION_NAME)
            for name in REFERENCE_TYPE_MAP
        ],
    )
    collection = client.collections.use(COLLECTION_NAME)
    original_insert = collection.data.insert

    def mock_insert(*args, **kwargs):
        return original_insert(*args, **kwargs, vector=[0.0] * 768)  # Mock embedding vector

    collection.data.insert = mock_insert
    chunks = [
        {
            "entity_id": "formula_1",
            "chunk_type": "numbered_formula",
            "content": "E=mc^2",
            "additional_info": "This is a famous formula.",
            "referenced_formulas": [],
        },
        {
            "entity_id": "text_1",
            "chunk_type": "text",
            "content": "Einstein's theory of relativity",
            "additional_field": "Some extra info",
            "referenced_formulas": ["formula_1"],
        },
    ]
    expected_directly_fetched = {
        "entity_id": "text_1",
        "chunk_type": "text",
        "content": "Einstein's theory of relativity",
        "additional_field": "Some extra info",
        "additional_info": None,
    }
    expected_fetched_by_reference = {
        "entity_id": "formula_1",
        "chunk_type": "numbered_formula",
        "content": "E=mc^2",
        "additional_info": "This is a famous formula.",
        "additional_field": None,
    }
    reference_map = build_reference_map(chunks)

    insert_chunks(collection, chunks, reference_map)
    response = collection.query.fetch_objects(
        filters=Filter.all_of(
            [
                Filter.by_property("entity_id").equal("text_1"),
                Filter.by_property("chunk_type").equal("text"),
            ]
        ),
        return_references=[
            QueryReference(
                link_on="referenced_formulas",
            ),
        ],
        limit=1,
    )

    directly_fetched = response.objects[0].properties
    fetched_by_reference = (
        response.objects[0].references["referenced_formulas"].objects[0].properties
    )
    assert directly_fetched == expected_directly_fetched
    assert fetched_by_reference == expected_fetched_by_reference
