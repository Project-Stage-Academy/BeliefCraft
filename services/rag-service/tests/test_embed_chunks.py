from unittest.mock import MagicMock, patch

import pytest
import weaviate
from rag_scripts.embed_chunks import (
    COLLECTION_NAME,
    REFERENCE_TYPE_MAP,
    build_reference_map,
    extract_references_from_chunk,
    generate_deterministic_uuid,
    insert_chunks,
    setup_collection,
)
from weaviate.collections.classes.config import Configure, ReferenceProperty
from weaviate.collections.classes.data import DataReference
from weaviate.collections.classes.filters import Filter
from weaviate.collections.classes.grpc import QueryReference


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


def test_insert_chunks_preserves_chunk_id_for_defined_in_references():
    """Verify that processing a chunk doesn't remove 'chunk_id' from the original list,
    preventing KeyErrors when later chunks reference it via 'defined_in_chunk'."""
    mock_collection = MagicMock()
    mock_batch = MagicMock()
    mock_collection.batch.dynamic.return_value.__enter__.return_value = mock_batch

    chunks = [
        {
            "chunk_id": "parent_id",
            "entity_id": "parent_entity",
            "chunk_type": "text",
            "content": "Parent content",
        },
        {
            "chunk_id": "child_id",
            "entity_id": "child_entity",
            "chunk_type": "text",
            "content": "Child content",
            "defined_in_chunk": "parent_id",
        },
    ]
    reference_map = {}

    insert_chunks(mock_collection, chunks, reference_map)

    assert chunks[0]["chunk_id"] == "parent_id"
    parent_canonical = {
        "entity_id": "parent_entity",
        "chunk_type": "text",
        "content": "Parent content",
    }
    parent_uuid = generate_deterministic_uuid(parent_canonical)
    added_child_properties = mock_batch.add_object.call_args_list[1].kwargs["properties"]
    assert added_child_properties["defined_in_chunk"] == parent_uuid
    # chunk_id now preserved for golden set validation
    assert added_child_properties["chunk_id"] == "child_id"


def test_defined_in_chunk_uuid_consistent_for_parent_without_entity_id():
    """Verify that when a parent chunk has no entity_id, the UUID stored in defined_in_chunk
    matches the UUID used when inserting the parent (repr without chunk_id)."""
    mock_collection = MagicMock()
    mock_batch = MagicMock()
    mock_collection.batch.dynamic.return_value.__enter__.return_value = mock_batch

    parent = {"chunk_id": "p1", "content": "raw parent text", "chunk_type": "text"}
    child = {
        "chunk_id": "c1",
        "content": "child text",
        "chunk_type": "text",
        "defined_in_chunk": "p1",
    }

    insert_chunks(mock_collection, [parent, child], {})

    # UUID now includes chunk_id when no entity_id
    parent_with_chunk_id = {"chunk_id": "p1", "content": "raw parent text", "chunk_type": "text"}
    expected_parent_uuid = generate_deterministic_uuid(parent_with_chunk_id)
    inserted_parent_uuid = mock_batch.add_object.call_args_list[0].kwargs["uuid"]
    # defined_in_chunk still uses canonical (without chunk_id) for reference resolution
    parent_canonical = {"content": "raw parent text", "chunk_type": "text"}
    expected_defined_in_uuid = generate_deterministic_uuid(parent_canonical)
    inserted_child_defined_in = mock_batch.add_object.call_args_list[1].kwargs["properties"][
        "defined_in_chunk"
    ]
    assert inserted_parent_uuid == expected_parent_uuid
    assert inserted_child_defined_in == expected_defined_in_uuid


def test_multiple_children_reference_same_parent_via_defined_in_chunk():
    """Verify that multiple child chunks referencing the same parent all receive the correct
    resolved UUID for defined_in_chunk, confirming the precomputed map handles this correctly."""
    mock_collection = MagicMock()
    mock_batch = MagicMock()
    mock_collection.batch.dynamic.return_value.__enter__.return_value = mock_batch

    parent = {
        "chunk_id": "shared_parent",
        "entity_id": "p_entity",
        "chunk_type": "text",
        "content": "Shared parent",
    }
    children = [
        {
            "chunk_id": f"child_{i}",
            "entity_id": f"child_entity_{i}",
            "chunk_type": "text",
            "content": f"Child {i}",
            "defined_in_chunk": "shared_parent",
        }
        for i in range(3)
    ]

    insert_chunks(mock_collection, [parent, *children], {})

    parent_canonical = {"entity_id": "p_entity", "chunk_type": "text", "content": "Shared parent"}
    expected_parent_uuid = generate_deterministic_uuid(parent_canonical)
    for call_idx in range(1, 4):
        props = mock_batch.add_object.call_args_list[call_idx].kwargs["properties"]
        assert props["defined_in_chunk"] == expected_parent_uuid


def test_chunk_uuid_computed_after_defined_in_chunk_correction():
    """Verify that for a chunk without entity_id, its UUID is based on the corrected
    defined_in_chunk value (a UUID string) rather than the original chunk_id string."""
    mock_collection = MagicMock()
    mock_batch = MagicMock()
    mock_collection.batch.dynamic.return_value.__enter__.return_value = mock_batch

    parent = {"chunk_id": "pid", "content": "parent", "chunk_type": "text"}
    child = {"chunk_id": "cid", "content": "child", "chunk_type": "text", "defined_in_chunk": "pid"}

    insert_chunks(mock_collection, [parent, child], {})

    # defined_in_chunk uses canonical parent (without chunk_id) for reference resolution
    parent_canonical = {"content": "parent", "chunk_type": "text"}
    parent_uuid_canonical = generate_deterministic_uuid(parent_canonical)

    # Child UUID includes chunk_id AND corrected defined_in_chunk
    corrected_child = {
        "chunk_id": "cid",
        "content": "child",
        "chunk_type": "text",
        "defined_in_chunk": parent_uuid_canonical,
    }
    expected_child_uuid = generate_deterministic_uuid(corrected_child)

    inserted_child_uuid = mock_batch.add_object.call_args_list[1].kwargs["uuid"]
    assert inserted_child_uuid == expected_child_uuid


def test_insert_chunks_skips_defined_in_chunk_when_parent_is_missing():
    """Verify that when defined_in_chunk references an unknown chunk_id, the field is dropped,
    the chunk is still inserted, and a warning is printed."""
    mock_collection = MagicMock()
    mock_batch = MagicMock()
    mock_collection.batch.dynamic.return_value.__enter__.return_value = mock_batch

    child = {
        "chunk_id": "c1",
        "content": "orphan child",
        "chunk_type": "text",
        "defined_in_chunk": "nonexistent_id",
    }

    with patch("builtins.print") as mock_print:
        insert_chunks(mock_collection, [child], {})

    mock_print.call_args_list[0].assert_called_with(
        "Warning: Chunk references unknown parent chunk_id='nonexistent_id' "
        "via 'defined_in_chunk'. Skipping field."
    )
    assert mock_batch.add_object.call_count == 1
    inserted_props = mock_batch.add_object.call_args_list[0].kwargs["properties"]
    assert "defined_in_chunk" not in inserted_props


def test_insert_chunks_warns_on_duplicate_uuid():
    """Verify that inserting two chunks that produce the same UUID prints a warning
    identifying the overwritten chunk, but both calls to add_object are still made."""
    mock_collection = MagicMock()
    mock_batch = MagicMock()
    mock_collection.batch.dynamic.return_value.__enter__.return_value = mock_batch

    identical_chunk = {"entity_id": "e1", "chunk_type": "text", "content": "same"}
    chunk_a = {"chunk_id": "a", **identical_chunk}
    chunk_b = {"chunk_id": "b", **identical_chunk}

    expected_uuid = generate_deterministic_uuid(identical_chunk)

    with patch("builtins.print") as mock_print:
        insert_chunks(mock_collection, [chunk_a, chunk_b], {})

    mock_print.call_args_list[0].assert_called_with(
        f"Warning: Duplicate UUID '{expected_uuid}' detected. "
        f"The previously inserted chunk with this UUID will be overwritten."
    )
    assert mock_batch.add_object.call_count == 2
