from unittest.mock import AsyncMock

import pytest
from rag_service.models import (
    Document,
    EntityType,
    MetadataFilter,
    MetadataFilters,
    SearchTags,
)
from rag_service.repositories import FakeDataRepository


@pytest.fixture
async def repo(settings):
    """Initialize FakeDataRepository with mock data."""
    async with FakeDataRepository(settings) as r:
        yield r


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


@pytest.mark.asyncio
async def test_fake_repo_get_related_code_definitions_not_supported(repo):
    """Verify FakeDataRepository raises NotImplementedError for code-definition retrieval."""
    with pytest.raises(NotImplementedError):
        await repo.get_related_code_definitions(["some-id"])


@pytest.mark.asyncio
async def test_fake_repository_in_filter_matches_list_metadata(repo):
    """Verify IN filter matches documents with list-valued metadata fields."""
    filters = MetadataFilters(
        filters=[
            MetadataFilter(field="referenced_formulas", operator="in", value=["3.1"]),
        ],
        condition="and",
    )

    results = await repo.vector_search(query="", k=10, filters=filters)

    ids = {doc.id for doc in results}
    assert "chunk_0001" in ids


@pytest.mark.asyncio
async def test_search_with_expansion_boosts_matching_tagged_documents(repo, monkeypatch):
    """Verify root search results use field-based similarity boosting."""
    documents = [
        Document(
            id="doc-low",
            content="low",
            cosine_similarity=0.8,
            metadata={"bc_concepts": [], "bc_db_tables": []},
        ),
        Document(
            id="doc-mid",
            content="mid",
            cosine_similarity=0.8,
            metadata={"bc_concepts": ["MULTI_AGENT_COORDINATION"], "bc_db_tables": []},
        ),
        Document(
            id="doc-high",
            content="high",
            cosine_similarity=0.8,
            metadata={
                "bc_concepts": ["MULTI_AGENT_COORDINATION"],
                "bc_db_tables": ["observations"],
            },
        ),
        Document(
            id="doc-very-low",
            content="very-low",
            cosine_similarity=0.8,
            metadata={"bc_concepts": [], "bc_db_tables": ["other_table"]},
        ),
    ]

    mocked_vector_search = AsyncMock(return_value=documents)
    monkeypatch.setattr(repo, "vector_search", mocked_vector_search)

    results = await repo.search_with_expansion(
        query="coordination",
        k=2,
        search_boosting=SearchTags(
            bc_concepts=["MULTI_AGENT_COORDINATION"],
            bc_db_tables=["observations"],
        ),
    )

    assert [doc.id for doc in results] == ["doc-high", "doc-mid"]
    assert results[0].cosine_similarity == pytest.approx(1.0)
    assert results[1].cosine_similarity == pytest.approx(0.9)
    assert mocked_vector_search.await_args.args[1] == 12


@pytest.mark.asyncio
async def test_search_with_expansion_keeps_order_without_boosting(repo, monkeypatch):
    """Verify root result order is unchanged when boosting is not provided."""
    documents = [
        Document(id="doc-1", content="1", metadata={"bc_concepts": ["X"]}),
        Document(id="doc-2", content="2", metadata={"bc_concepts": ["Y"]}),
    ]

    mocked_vector_search = AsyncMock(return_value=documents)
    monkeypatch.setattr(repo, "vector_search", mocked_vector_search)

    results = await repo.search_with_expansion(query="x", k=2)

    assert [doc.id for doc in results] == ["doc-1", "doc-2"]
    assert mocked_vector_search.await_args.args[1] == 2
