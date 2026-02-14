"""
Unit tests for RAG tools.

Tests all 3 RAG tools:
- SearchKnowledgeBaseTool
- ExpandGraphByIdsTool
- GetEntityByNumberTool
"""

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from app.tools.rag_tools import (
    ExpandGraphByIdsTool,
    GetEntityByNumberTool,
    SearchKnowledgeBaseTool,
)


@pytest.fixture
def mock_rag_client() -> AsyncMock:
    """Create mock RAGAPIClient."""
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock()
    return client


class TestSearchKnowledgeBaseTool:
    """Tests for SearchKnowledgeBaseTool."""

    @pytest.mark.asyncio
    async def test_metadata(self) -> None:
        """Test tool metadata is correct."""
        tool = SearchKnowledgeBaseTool()
        metadata = tool.get_metadata()

        assert metadata.name == "search_knowledge_base"
        assert metadata.category == "rag"
        assert (
            "knowledge" in metadata.description.lower()
            or "algorithm" in metadata.description.lower()
        )
        assert "query" in metadata.parameters["properties"]
        assert "k" in metadata.parameters["properties"]
        assert "traverse_types" in metadata.parameters["properties"]
        assert "filters" in metadata.parameters["properties"]
        assert metadata.parameters["required"] == ["query"]

    @pytest.mark.asyncio
    async def test_execute_basic_search(self, mock_rag_client: AsyncMock) -> None:
        """Test basic search without optional parameters."""
        tool = SearchKnowledgeBaseTool()

        mock_response: dict[str, Any] = {
            "results": [
                {"id": "doc1", "text": "Inventory control...", "score": 0.95},
                {"id": "doc2", "text": "POMDP algorithms...", "score": 0.87},
            ],
            "total": 2,
        }
        mock_rag_client.search_knowledge_base.return_value = mock_response

        with patch("app.tools.rag_tools.RAGAPIClient", return_value=mock_rag_client):
            result = await tool.execute(query="inventory control")

            assert result == mock_response
            mock_rag_client.search_knowledge_base.assert_called_once_with(
                query="inventory control", k=5, traverse_types=None, filters=None
            )

    @pytest.mark.asyncio
    async def test_execute_search_with_all_params(self, mock_rag_client: AsyncMock) -> None:
        """Test search with all optional parameters."""
        tool = SearchKnowledgeBaseTool()

        mock_response: dict[str, Any] = {
            "results": [{"id": "doc1", "text": "Chapter 16 POMDP", "score": 0.99}],
            "total": 1,
        }
        mock_rag_client.search_knowledge_base.return_value = mock_response

        with patch("app.tools.rag_tools.RAGAPIClient", return_value=mock_rag_client):
            result = await tool.execute(
                query="POMDP belief update",
                k=10,
                traverse_types=["formula", "algorithm_code"],
                filters={"chapter": "16"},
            )

            assert result == mock_response
            mock_rag_client.search_knowledge_base.assert_called_once_with(
                query="POMDP belief update",
                k=10,
                traverse_types=["formula", "algorithm_code"],
                filters={"chapter": "16"},
            )

    @pytest.mark.asyncio
    async def test_execute_empty_results(self, mock_rag_client: AsyncMock) -> None:
        """Test search with no results."""
        tool = SearchKnowledgeBaseTool()

        mock_response: dict[str, Any] = {"results": [], "total": 0}
        mock_rag_client.search_knowledge_base.return_value = mock_response

        with patch("app.tools.rag_tools.RAGAPIClient", return_value=mock_rag_client):
            result = await tool.execute(query="nonexistent topic")

            assert result["total"] == 0
            assert result["results"] == []

    @pytest.mark.asyncio
    async def test_to_openai_function(self) -> None:
        """Test conversion to OpenAI function schema."""
        tool = SearchKnowledgeBaseTool()
        schema = tool.to_openai_function()

        assert schema["type"] == "function"
        assert schema["function"]["name"] == "search_knowledge_base"
        assert "query" in schema["function"]["parameters"]["properties"]


class TestExpandGraphByIdsTool:
    """Tests for ExpandGraphByIdsTool."""

    @pytest.mark.asyncio
    async def test_metadata(self) -> None:
        """Test tool metadata is correct."""
        tool = ExpandGraphByIdsTool()
        metadata = tool.get_metadata()

        assert metadata.name == "expand_graph_by_ids"
        assert metadata.category == "rag"
        assert (
            "linked" in metadata.description.lower() or "entities" in metadata.description.lower()
        )
        assert "document_ids" in metadata.parameters["properties"]
        assert "traverse_types" in metadata.parameters["properties"]
        assert metadata.parameters["required"] == ["document_ids"]

    @pytest.mark.asyncio
    async def test_execute_without_traverse_types(self, mock_rag_client: AsyncMock) -> None:
        """Test graph expansion without traverse types."""
        tool = ExpandGraphByIdsTool()

        mock_response: dict[str, Any] = {
            "expanded": [
                {"id": "formula_3_2", "type": "formula", "content": "s < S policy"},
                {"id": "algo_3_2", "type": "algorithm", "content": "def policy()..."},
            ],
            "relationships": [{"from": "doc1", "to": "formula_3_2", "type": "REFERENCES"}],
        }
        mock_rag_client.expand_graph_by_ids.return_value = mock_response

        with patch("app.tools.rag_tools.RAGAPIClient", return_value=mock_rag_client):
            result = await tool.execute(document_ids=["doc1", "doc2"])

            assert result == mock_response
            mock_rag_client.expand_graph_by_ids.assert_called_once_with(
                document_ids=["doc1", "doc2"], traverse_types=None
            )

    @pytest.mark.asyncio
    async def test_execute_with_traverse_types(self, mock_rag_client: AsyncMock) -> None:
        """Test graph expansion with specific traverse types."""
        tool = ExpandGraphByIdsTool()

        mock_response: dict[str, Any] = {"expanded": [], "relationships": []}
        mock_rag_client.expand_graph_by_ids.return_value = mock_response

        with patch("app.tools.rag_tools.RAGAPIClient", return_value=mock_rag_client):
            result = await tool.execute(
                document_ids=["doc1"], traverse_types=["formula", "table", "algorithm_code"]
            )

            assert result == mock_response
            mock_rag_client.expand_graph_by_ids.assert_called_once_with(
                document_ids=["doc1"], traverse_types=["formula", "table", "algorithm_code"]
            )

    @pytest.mark.asyncio
    async def test_execute_single_document(self, mock_rag_client: AsyncMock) -> None:
        """Test expansion with single document ID."""
        tool = ExpandGraphByIdsTool()

        mock_response: dict[str, Any] = {
            "expanded": [{"id": "formula_16_4", "type": "formula", "content": "P(x|z)"}]
        }
        mock_rag_client.expand_graph_by_ids.return_value = mock_response

        with patch("app.tools.rag_tools.RAGAPIClient", return_value=mock_rag_client):
            result = await tool.execute(document_ids=["doc_pomdp"])

            assert len(result["expanded"]) == 1


class TestGetEntityByNumberTool:
    """Tests for GetEntityByNumberTool."""

    @pytest.mark.asyncio
    async def test_metadata(self) -> None:
        """Test tool metadata is correct."""
        tool = GetEntityByNumberTool()
        metadata = tool.get_metadata()

        assert metadata.name == "get_entity_by_number"
        assert metadata.category == "rag"
        assert "entity" in metadata.description.lower() or "number" in metadata.description.lower()
        assert "entity_type" in metadata.parameters["properties"]
        assert "number" in metadata.parameters["properties"]
        assert metadata.parameters["required"] == ["entity_type", "number"]

    @pytest.mark.asyncio
    async def test_execute_get_formula(self, mock_rag_client: AsyncMock) -> None:
        """Test retrieving a formula by number."""
        tool = GetEntityByNumberTool()

        mock_response: dict[str, Any] = {
            "entity_type": "formula",
            "number": "16.4",
            "content": "P(x|z) = P(z|x)P(x) / P(z)",
            "title": "Bayesian Update",
            "chapter": "16",
        }
        mock_rag_client.get_entity_by_number.return_value = mock_response

        with patch("app.tools.rag_tools.RAGAPIClient", return_value=mock_rag_client):
            result = await tool.execute(entity_type="formula", number="16.4")

            assert result == mock_response
            mock_rag_client.get_entity_by_number.assert_called_once_with(
                entity_type="formula", number="16.4"
            )

    @pytest.mark.asyncio
    async def test_execute_get_algorithm(self, mock_rag_client: AsyncMock) -> None:
        """Test retrieving an algorithm by number."""
        tool = GetEntityByNumberTool()

        mock_response: dict[str, Any] = {
            "entity_type": "algorithm",
            "number": "3.2",
            "content": "function inventory_policy(s, S)...",
            "title": "(s,S) Inventory Policy",
            "chapter": "3",
        }
        mock_rag_client.get_entity_by_number.return_value = mock_response

        with patch("app.tools.rag_tools.RAGAPIClient", return_value=mock_rag_client):
            result = await tool.execute(entity_type="algorithm", number="3.2")

            assert result["entity_type"] == "algorithm"
            assert result["number"] == "3.2"

    @pytest.mark.asyncio
    async def test_execute_get_table(self, mock_rag_client: AsyncMock) -> None:
        """Test retrieving a table by number."""
        tool = GetEntityByNumberTool()

        mock_response: dict[str, Any] = {
            "entity_type": "table",
            "number": "5.1",
            "content": {"headers": ["Method", "Risk"], "rows": [["CVaR", "0.95"]]},
            "title": "Risk Assessment Methods",
        }
        mock_rag_client.get_entity_by_number.return_value = mock_response

        with patch("app.tools.rag_tools.RAGAPIClient", return_value=mock_rag_client):
            result = await tool.execute(entity_type="table", number="5.1")

            assert result["entity_type"] == "table"


class TestToolIntegration:
    """Integration tests for all RAG tools."""

    @pytest.mark.asyncio
    async def test_all_tools_have_correct_category(self) -> None:
        """Test that all tools have 'rag' category."""
        tools = [
            SearchKnowledgeBaseTool(),
            ExpandGraphByIdsTool(),
            GetEntityByNumberTool(),
        ]

        for tool in tools:
            assert tool.metadata.category == "rag"

    @pytest.mark.asyncio
    async def test_all_tools_have_openai_schemas(self) -> None:
        """Test that all tools can generate OpenAI function schemas."""
        tools = [
            SearchKnowledgeBaseTool(),
            ExpandGraphByIdsTool(),
            GetEntityByNumberTool(),
        ]

        for tool in tools:
            schema = tool.to_openai_function()
            assert schema["type"] == "function"
            assert "function" in schema
            assert "name" in schema["function"]
            assert "description" in schema["function"]
            assert "parameters" in schema["function"]

    @pytest.mark.asyncio
    async def test_tool_run_wrapper_success(self, mock_rag_client: AsyncMock) -> None:
        """Test that BaseTool.run() wrapper works correctly."""
        tool = SearchKnowledgeBaseTool()

        mock_response: dict[str, Any] = {"results": [], "total": 0}
        mock_rag_client.search_knowledge_base.return_value = mock_response

        with patch("app.tools.rag_tools.RAGAPIClient", return_value=mock_rag_client):
            result = await tool.run(query="test query")

            assert result.success is True
            assert result.data == mock_response
            assert result.execution_time_ms > 0
            assert result.error is None

    @pytest.mark.asyncio
    async def test_tool_run_wrapper_error(self) -> None:
        """Test that BaseTool.run() handles errors correctly."""
        tool = SearchKnowledgeBaseTool()

        # Create a mock that raises exception when method is called
        async def mock_search(*args: Any, **kwargs: Any) -> None:
            raise Exception("RAG API Error")

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.search_knowledge_base = mock_search

        with patch("app.tools.rag_tools.RAGAPIClient", return_value=mock_client):
            result = await tool.run(query="test")

            assert result.success is False
            assert result.data is None
            assert result.error is not None
            assert "RAG API Error" in result.error
            assert result.execution_time_ms > 0

    @pytest.mark.asyncio
    async def test_search_and_expand_workflow(self, mock_rag_client: AsyncMock) -> None:
        """Test typical workflow: search then expand."""
        search_tool = SearchKnowledgeBaseTool()
        expand_tool = ExpandGraphByIdsTool()

        # Mock search results
        search_response: dict[str, Any] = {
            "results": [
                {"id": "doc1", "text": "Inventory policy...", "score": 0.95},
                {"id": "doc2", "text": "MDP formulation...", "score": 0.88},
            ]
        }
        mock_rag_client.search_knowledge_base.return_value = search_response

        # Mock expansion results
        expand_response: dict[str, Any] = {
            "expanded": [
                {"id": "formula_3_2", "type": "formula"},
                {"id": "algo_3_2", "type": "algorithm"},
            ]
        }
        mock_rag_client.expand_graph_by_ids.return_value = expand_response

        with patch("app.tools.rag_tools.RAGAPIClient", return_value=mock_rag_client):
            # Step 1: Search
            search_result = await search_tool.execute(query="inventory control")
            assert len(search_result["results"]) == 2

            # Step 2: Expand from search results
            doc_ids = [r["id"] for r in search_result["results"]]
            expand_result = await expand_tool.execute(
                document_ids=doc_ids, traverse_types=["formula", "algorithm_code"]
            )
            assert len(expand_result["expanded"]) == 2
