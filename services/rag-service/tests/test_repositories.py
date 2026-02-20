import pytest
from rag_service.models import EntityType, MetadataFilter, MetadataFilters
from rag_service.repositories import FakeDataRepository


@pytest.fixture
def repo(settings):
    """Initialize FakeDataRepository with mock data."""
    return FakeDataRepository(settings)


@pytest.mark.asyncio
async def test_expand_graph_by_ids(repo):
    """
    Verify that expand_graph_by_ids correctly traverses metadata links.
    Chunk 0001 has referenced_formulas: ["3.1"] and referenced_algorithms: ["2.1"]
    and referenced_figures: ["7.1"]. We want to traverse formulas and algorithms, but not figures.
    """
    document_ids = ["chunk_0001"]
    traverse_types = [EntityType.FORMULA, EntityType.ALGORITHM]

    expanded_docs = await repo.expand_graph_by_ids(document_ids, traverse_types)

    # Based on mock data:
    # 3.1 is chunk_0021
    # 2.1 is chunk_0011
    assert len(expanded_docs) == 2
    ids = {doc.id for doc in expanded_docs}
    assert "chunk_0021" in ids  # formula 3.1
    assert "chunk_0011" in ids  # algorithm 2.1
    assert "chunk_0061" not in ids  # should not include referenced_figures

    # Verify types
    for doc in expanded_docs:
        assert doc.metadata["chunk_type"] in ["numbered_formula", "algorithm"]


@pytest.mark.asyncio
async def test_search_with_expansion(repo):
    """
    Verify search_with_expansion combines semantic search results with graph links.
    """
    # Mock vector_search to return chunk_0001
    query = "joint distribution"
    k = 1
    traverse_types = [EntityType.FORMULA]

    results = await repo.search_with_expansion(
        query,
        k,
        traverse_types=traverse_types,
        filters=MetadataFilters(  # filter to ensure we get chunk_0001
            filters=[
                MetadataFilter(
                    field="subsection_title", operator="eq", value="Joint Distributions"
                ),
            ],
            condition="and",
        ),
    )

    # Should have chunk_0001 and its linked formula chunk_0021
    assert len(results) == 2
    ids = {doc.id for doc in results}
    assert "chunk_0001" in ids
    assert "chunk_0021" in ids


@pytest.mark.asyncio
async def test_expand_graph_empty_input(repo):
    """Verify expansion handles empty inputs gracefully."""
    assert await repo.expand_graph_by_ids([], [EntityType.FORMULA]) == []
    assert await repo.expand_graph_by_ids(["id"], []) == []
