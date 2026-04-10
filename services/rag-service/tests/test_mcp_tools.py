from typing import get_args
from unittest.mock import AsyncMock, MagicMock

import pytest
from rag_service.mcp_tools import (
    ALLOWED_CONCEPT_CATEGORIES,
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
    """Verify search_knowledge_base tool delegates correctly to the repository."""
    mock_repo.search_with_expansion.return_value = [MagicMock(id="doc1")]

    await rag_tools.search_knowledge_base(
        query="test query",
        k=3,
        traverse_types=[EntityType.FORMULA],
        filters=SearchFilters(part="I"),
    )

    # Check if repository was called with converted filters
    args, kwargs = mock_repo.search_with_expansion.call_args
    assert args[0] == "test query"
    assert args[1] == 3
    # Check converted filters
    filters = args[2]
    assert filters.filters[0].field == "part"
    assert filters.filters[0].value == "I"
    assert args[3] == [EntityType.FORMULA]
    assert args[4] is None


@pytest.mark.asyncio
async def test_search_knowledge_base_passes_search_tags(rag_tools, mock_repo):
    """Verify explicit search_tags is forwarded as boosting config."""
    mock_repo.search_with_expansion.return_value = [MagicMock(id="doc1")]

    await rag_tools.search_knowledge_base(
        query="test query",
        search_tags=SearchTags(
            bc_concepts=["SENSOR_FUSION_STATE_ESTIMATION"],
            bc_db_tables=["sensor_devices", "observations"],
        ),
    )

    args, kwargs = mock_repo.search_with_expansion.call_args
    assert args[2] is None
    assert args[3] is None
    assert args[4] == SearchTags(
        bc_concepts=["SENSOR_FUSION_STATE_ESTIMATION"],
        bc_db_tables=["sensor_devices", "observations"],
    )


@pytest.mark.asyncio
async def test_search_knowledge_base_passes_explicit_search_tags(rag_tools, mock_repo):
    """Verify explicit search_tags argument is forwarded to repository."""
    mock_repo.search_with_expansion.return_value = [MagicMock(id="doc1")]

    await rag_tools.search_knowledge_base(
        query="test query",
        filters=SearchFilters(part="I"),
        search_tags=SearchTags(
            bc_concepts=["SENSOR_FUSION_STATE_ESTIMATION"],
            bc_db_tables=["sensor_devices", "observations"],
        ),
    )

    args, kwargs = mock_repo.search_with_expansion.call_args
    assert args[2] is not None
    assert args[3] is None
    assert args[4] == SearchTags(
        bc_concepts=["SENSOR_FUSION_STATE_ESTIMATION"],
        bc_db_tables=["sensor_devices", "observations"],
    )


@pytest.mark.asyncio
async def test_search_knowledge_base_ignores_empty_search_tags(rag_tools, mock_repo):
    """Verify empty search_tags payload is normalized to None."""
    mock_repo.search_with_expansion.return_value = [MagicMock(id="doc1")]

    await rag_tools.search_knowledge_base(
        query="test query",
        filters=SearchFilters(part="I"),
        search_tags=SearchTags(),
    )

    args, kwargs = mock_repo.search_with_expansion.call_args
    assert args[2] is not None
    assert args[3] is None
    assert args[4] is None


@pytest.mark.asyncio
async def test_get_entity_by_number_delegation(rag_tools, mock_repo):
    """Verify get_entity_by_number constructs precise filters for lookup."""
    mock_repo.vector_search.return_value = [MagicMock(id="doc1")]

    await rag_tools.get_entity_by_number(entity_type=EntityType.FORMULA, number="3.1")

    # Verify the precise filter construction
    args, kwargs = mock_repo.vector_search.call_args
    assert args[0] == ""
    assert kwargs["k"] == 1
    filters = kwargs["filters"]

    field_values = {f.field: f.value for f in filters.filters}
    assert field_values["chunk_type"] == "numbered_formula"
    assert field_values["entity_id"] == "3.1"


@pytest.mark.asyncio
async def test_get_entity_by_number_returns_sentinel_document_when_missing(rag_tools, mock_repo):
    """
    Verify get_entity_by_number returns a Document with found=false when repository has no hit.
    """
    mock_repo.vector_search.return_value = []

    result = await rag_tools.get_entity_by_number(entity_type=EntityType.TABLE, number="99.9")

    assert isinstance(result, Document)
    assert result.content == ""
    assert result.metadata == {
        "found": False,
        "entity_type": "table",
        "number": "99.9",
    }


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
    category = "PROBABILISTIC_INFERENCE"

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


def test_concept_tag_category_literal_matches_json_categories():
    """Verify ConceptTagCategory literal stays synchronized with concept_tags.json categories."""
    assert set(get_args(ConceptTagCategory)) == set(CONCEPT_TAGS_BY_CATEGORY.keys())
    assert set(CONCEPT_TAGS_BY_CATEGORY.keys()) == ALLOWED_CONCEPT_CATEGORIES
