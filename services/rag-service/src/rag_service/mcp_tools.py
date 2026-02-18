from typing import Annotated

from common.logging import get_logger
from fastmcp import FastMCP

from .models import Document, EntityType, MetadataFilter, MetadataFilters, SearchFilters
from .repositories import AbstractVectorStoreRepository

BOOK_CONTENTS = """part i probabilistic reasoning
2 Representation 19
3 Inference 43
4 Parameter Learning 71
5 Structure Learning 97
6 Simple Decisions 111
part ii sequential problems
7 Exact Solution Methods 133
8 Approximate Value Functions 161
9 Online Planning 181
10 Policy Search 213
11 Policy Gradient Estimation 231
12 Policy Gradient Optimization 249
13 Actor-Critic Methods 267
14 Policy Validation 281
part iii model uncertainty
15 Exploration and Exploitation 299
16 Model-Based Methods 317
17 Model-Free Methods 335
18 Imitation Learning 355
part iv state uncertainty
19 Beliefs 379
20 Exact Belief State Planning 407
21 Offline Belief State Planning 427
22 Online Belief State Planning 453
23 Controller Abstractions 471
part v multiagent systems
24 Multiagent Reasoning 493
25 Sequential Problems 517
26 State Uncertainty 533
27 Collaborative Agents 545
appendices
A Mathematical Concepts 561
B Probability Distributions 573
C Computational Complexity 575
D Neural Representations 581
E Search Algorithms 599
F Problems 609"""

logger = get_logger(__name__)

SEARCH_FILTER_FIELD_TO_METADATA_FIELD = {
    "part": "part_number",
    "section": "section_number",
    "subsection": "subsection_number",
    "subsubsection": "subsubsection_number",
    "page_number": "page",
}


class RagTools:
    tools = ["search_knowledge_base", "expand_graph_by_ids", "get_entity_by_number"]

    def __init__(self, repository: AbstractVectorStoreRepository) -> None:
        self._repository = repository

    @staticmethod
    def _convert_search_filters(filters: SearchFilters | None) -> MetadataFilters | None:
        """Convert tool-level SearchFilters to repository-level MetadataFilters."""
        if filters is None:
            return None

        metadata_filters: list[MetadataFilter] = []

        for filter_field, metadata_field in SEARCH_FILTER_FIELD_TO_METADATA_FIELD.items():
            value = getattr(filters, filter_field)
            if value is not None:
                metadata_filters.append(
                    MetadataFilter(field=metadata_field, operator="eq", value=value)
                )

        if not metadata_filters:
            return None

        return MetadataFilters(filters=metadata_filters, condition="and")

    async def search_knowledge_base(
        self,
        query: Annotated[str, "Text query for semantic search."],
        k: Annotated[int, "Number of initial relevant documents (top_k)."] = 5,
        traverse_types: Annotated[
            list[EntityType] | None,
            "Types of objects for search results expansion via links.",
        ] = None,
        filters: Annotated[
            SearchFilters | None,
            "Metadata filters to restrict search scope .",
        ] = None,
    ) -> list[Document]:
        """Universal knowledge base search.
        Performs semantic search of k documents and optionally
        retrieves linked objects based on traverse_types.
        """
        logger.info(
            "rag tool call",
            tool="search_knowledge_base",
            query_len=len(query),
            k=k,
            traverse_types=[t.value for t in traverse_types] if traverse_types else [],
            filters=filters.model_dump() if filters else None,
        )
        metadata_filters = self._convert_search_filters(filters)
        documents = await self._repository.search_with_expansion(
            query, k, metadata_filters, traverse_types
        )
        logger.info(
            "rag tool result",
            tool="search_knowledge_base",
            num_documents=len(documents),
        )
        return documents

    async def expand_graph_by_ids(
        self,
        document_ids: Annotated[list[str], "List of document IDs to expand from."],
        traverse_types: Annotated[
            list[EntityType],
            "Types of linked objects to retrieve.",
        ],
    ) -> list[Document]:
        """
        Retrieve linked objects for specific document IDs.
        """
        logger.info(
            "rag tool call",
            tool="expand_graph_by_ids",
            document_ids=document_ids,
            traverse_types=[t.value for t in traverse_types] if traverse_types else [],
        )
        documents = await self._repository.expand_graph_by_ids(document_ids, traverse_types)
        logger.info(
            "rag tool result",
            tool="expand_graph_by_ids",
            num_documents=len(documents),
        )
        return documents

    async def get_entity_by_number(
        self,
        entity_type: Annotated[EntityType, "Type of entity."],
        number: Annotated[str, "Unique number of the object, e.g. '1.2.4'."],
    ) -> Document | None:
        """
        Precise retrieval of a unique object by its number. Returns None if not found.
        """
        logger.info(
            "rag tool call",
            tool="get_entity_by_number",
            entity_type=entity_type.value,
            number=number,
        )
        filters = MetadataFilters(
            filters=[
                MetadataFilter(field="chunk_type", operator="eq", value=entity_type),
                MetadataFilter(field="entity_id", operator="eq", value=number),
            ],
            condition="and",
        )
        results = await self._repository.vector_search("", k=1, filters=filters)
        if results:
            logger.info(
                "rag tool result",
                tool="get_entity_by_number",
                found=True,
            )
            return results[0]
        logger.info(
            "rag tool result",
            tool="get_entity_by_number",
            found=False,
        )
        return None


def create_mcp_server(repository: AbstractVectorStoreRepository) -> FastMCP:
    """Create MCP server and register tools."""
    mcp = FastMCP(
        "'Algorithms for Decision Making' book RAG",
        instructions="""
Book contents:
part number title
section_number title page
""" + BOOK_CONTENTS,
    )
    rag_tools = RagTools(repository)
    for tool_name in RagTools.tools:
        mcp.tool(getattr(rag_tools, tool_name))
    return mcp
