from unittest.mock import AsyncMock, MagicMock

import pytest
from rag_service.mcp_tools import (
    CONCEPT_TAGS_BY_CATEGORY,
    RagTools,
)
from rag_service.models import (
    SUPPORTED_DB_TABLES,
    ConceptTagCategory,
    Document,
    EntityType,
    SearchFilters,
    SearchTags,
)


@pytest.fixture
def mock_repo():
    """Mock repository for testing tool delegation."""
    return AsyncMock()


@pytest.fixture
def rag_tools(mock_repo):
    """RagTools instance with mocked repository."""
    return RagTools(mock_repo)


def test_convert_search_filters():
    """Verify conversion of SearchFilters to internal MetadataFilters."""
    filters = SearchFilters(part="I", page_number=15)

    internal_filters = RagTools._convert_search_filters(filters)

    assert internal_filters.condition == "and"
    fields = {f.field: f.value for f in internal_filters.filters}
    assert fields["part"] == "I"
    assert fields["page"] == 15
    assert "section_number" not in fields
    assert "subsection_number" not in fields
    assert "subsubsection_number" not in fields


def test_convert_search_filters_uses_only_metadata_fields():
    """Verify only metadata fields contribute to filter conversion."""
    filters = SearchFilters(part="I")

    internal_filters = RagTools._convert_search_filters(filters)

    assert internal_filters is not None
    assert [f.field for f in internal_filters.filters] == ["part"]


def test_extract_search_tags_from_explicit_parameter():
    """Verify explicit search_tags parameter is used when provided."""
    tags = RagTools._extract_search_tags(
        SearchTags(
            bc_concepts=["SENSOR_FUSION_STATE_ESTIMATION"],
            bc_db_tables=["observations"],
        )
    )

    assert tags == SearchTags(
        bc_concepts=["SENSOR_FUSION_STATE_ESTIMATION"],
        bc_db_tables=["observations"],
    )


def test_extract_search_tags_returns_none_for_empty_payload():
    """Verify empty explicit search_tags payload is treated as no tags."""
    assert RagTools._extract_search_tags(SearchTags()) is None


@pytest.mark.asyncio
async def test_search_knowledge_base_delegation(rag_tools, mock_repo):
    """Verify search_knowledge_base performs root search with converted filters."""
    mock_repo.vector_search.return_value = [MagicMock(id="doc1")]
    mock_repo.expand_graph_by_ids.return_value = []

    await rag_tools.search_knowledge_base(
        query="test query",
        k=3,
        traverse_types=[EntityType.FORMULA],
        filters=SearchFilters(part="I"),
    )

    args, _ = mock_repo.vector_search.call_args
    assert args[0] == "test query"
    assert args[1] == 3
    filters = args[2]
    assert filters.filters[0].field == "part"
    assert filters.filters[0].value == "I"
    mock_repo.expand_graph_by_ids.assert_awaited_once_with(["doc1"], [EntityType.FORMULA])


@pytest.mark.asyncio
async def test_search_knowledge_base_boosts_matching_tagged_documents(rag_tools, mock_repo):
    """Verify root result ranking and candidate size are controlled in MCP layer."""
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
    mock_repo.vector_search.return_value = documents
    mock_repo.expand_graph_by_ids.return_value = []

    results = await rag_tools.search_knowledge_base(
        query="coordination",
        k=2,
        search_tags=SearchTags(
            bc_concepts=["MULTI_AGENT_COORDINATION"],
            bc_db_tables=["observations"],
        ),
    )

    assert [doc.id for doc in results] == ["doc-high", "doc-mid"]
    assert results[0].cosine_similarity == pytest.approx(1.0)
    assert results[1].cosine_similarity == pytest.approx(0.9)
    assert mock_repo.vector_search.await_args.args[1] == 12


@pytest.mark.asyncio
async def test_search_knowledge_base_ignores_empty_search_tags(rag_tools, mock_repo):
    """Verify empty search_tags payload is normalized to None without candidate widening."""
    mock_repo.vector_search.return_value = [Document(id="doc1", content="x")]
    mock_repo.expand_graph_by_ids.return_value = []

    await rag_tools.search_knowledge_base(
        query="test query",
        filters=SearchFilters(part="I"),
        search_tags=SearchTags(),
    )

    args, _ = mock_repo.vector_search.call_args
    assert args[1] == 5


@pytest.mark.asyncio
async def test_search_knowledge_base_deduplicates_root_and_expanded(rag_tools, mock_repo):
    """Verify duplicate IDs are removed while preserving root-first order."""
    root = Document(id="doc1", content="root", metadata={})
    duplicate_root = Document(id="doc1", content="expanded duplicate", metadata={})
    expanded = Document(id="doc2", content="expanded", metadata={})

    mock_repo.vector_search.return_value = [root]
    mock_repo.expand_graph_by_ids.return_value = [duplicate_root, expanded]

    results = await rag_tools.search_knowledge_base(
        query="test query",
        traverse_types=[EntityType.FORMULA],
    )

    assert [doc.id for doc in results] == ["doc1", "doc2"]


@pytest.mark.asyncio
async def test_get_entity_by_number_delegation(rag_tools, mock_repo):
    """Verify get_entity_by_number constructs precise filters for lookup."""
    mock_repo.vector_search.return_value = [MagicMock(id="doc1")]

    await rag_tools.get_entity_by_number(entity_type=EntityType.FORMULA, number="3.1")

    args, kwargs = mock_repo.vector_search.call_args
    assert args[0] == ""
    assert kwargs["k"] == 1
    filters = kwargs["filters"]

    field_values = {f.field: f.value for f in filters.filters}
    assert field_values["chunk_type"] == "numbered_formula"
    assert field_values["entity_id"] == "3.1"


@pytest.mark.asyncio
async def test_get_related_code_definitions_delegation(rag_tools, mock_repo):
    """Verify get_related_code_definitions delegates to the repository and returns one document."""
    expected_document = Document(
        content="def foo():\n    pass",
        cosine_similarity=None,
    )
    mock_repo.get_related_code_definitions.return_value = expected_document

    result = await rag_tools.get_related_code_definitions(document_ids=["doc-uuid-001"])

    mock_repo.get_related_code_definitions.assert_called_once_with(["doc-uuid-001"])
    assert isinstance(result, Document)
    assert result == expected_document


@pytest.mark.asyncio
async def test_get_related_code_definitions_empty_ids(rag_tools, mock_repo):
    """Verify get_related_code_definitions passes empty list to repository."""
    expected_document = Document(
        content="",
        cosine_similarity=None,
    )
    mock_repo.get_related_code_definitions.return_value = expected_document

    result = await rag_tools.get_related_code_definitions(document_ids=[])

    mock_repo.get_related_code_definitions.assert_called_once_with([])
    assert isinstance(result, Document)
    assert result == expected_document


@pytest.mark.asyncio
async def test_get_related_code_definitions_multiple_ids(rag_tools, mock_repo):
    """Verify get_related_code_definitions delegates correctly with multiple IDs."""
    expected_document = Document(
        content="def foo():\n    pass\n\n\ndef bar():\n    return 1",
        cosine_similarity=None,
    )
    mock_repo.get_related_code_definitions.return_value = expected_document

    result = await rag_tools.get_related_code_definitions(
        document_ids=["doc-uuid-001", "doc-uuid-002"]
    )

    mock_repo.get_related_code_definitions.assert_called_once_with(["doc-uuid-001", "doc-uuid-002"])
    assert isinstance(result, Document)
    assert result == expected_document


@pytest.mark.asyncio
async def test_get_search_tags_catalog_returns_concepts_only(rag_tools):
    """Verify catalog tool can return concepts only."""
    result = await rag_tools.get_search_tags_catalog(tag_type="concepts")

    expected_concepts = [
        tag for category_tags in CONCEPT_TAGS_BY_CATEGORY.values() for tag in category_tags
    ]
    assert isinstance(result, Document)
    assert result.metadata == {
        "tag_type": "concepts",
        "selected_category": None,
        "items": expected_concepts,
    }


@pytest.mark.asyncio
async def test_get_search_tags_catalog_filters_concepts_by_category(rag_tools):
    """Verify category filter is applied in concepts mode."""
    category: ConceptTagCategory = "PROBABILISTIC_INFERENCE"

    result = await rag_tools.get_search_tags_catalog(tag_type="concepts", category=category)

    assert result.metadata == {
        "tag_type": "concepts",
        "selected_category": category,
        "items": CONCEPT_TAGS_BY_CATEGORY[category],
    }


@pytest.mark.asyncio
async def test_get_search_tags_catalog_returns_tables_only(rag_tools):
    """Verify catalog tool can return DB tables only."""
    result = await rag_tools.get_search_tags_catalog(tag_type="tables")

    assert result.metadata == {
        "tag_type": "tables",
        "selected_category": None,
        "items": SUPPORTED_DB_TABLES,
    }
