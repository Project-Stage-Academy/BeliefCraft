from unittest.mock import AsyncMock, MagicMock

import pytest
from rag_service.mcp_tools import RagTools
from rag_service.models import EntityType, SearchFilters


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
    assert fields["part_number"] == "I"
    assert fields["page"] == 15
    assert "section_number" not in fields
    assert "subsection_number" not in fields
    assert "subsubsection_number" not in fields


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
    assert filters.filters[0].field == "part_number"
    assert filters.filters[0].value == "I"
    assert args[3] == [EntityType.FORMULA]


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
