import json
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Annotated, Literal, get_args

from common.logging import get_logger
from fastmcp import FastMCP
from fastmcp.server.lifespan import lifespan

from .constants import ENTITY_TYPE_TO_CHUNK_TYPE
from .models import (
    SUPPORTED_DB_TABLES,
    ConceptTagCategory,
    Document,
    EntityType,
    MetadataFilter,
    MetadataFilterOperator,
    MetadataFilters,
    SearchFilters,
    SearchTags,
    SearchTagsCatalogMetadata,
)
from .repositories import AbstractVectorStoreRepository
from .search_boosting import SearchResultBooster

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
    "part": "part",
    "section": "section_number",
    "subsection": "subsection_number",
    "subsubsection": "subsubsection_number",
    "page_number": "page",
}

CONCEPT_TAGS_PATH = Path(__file__).with_name("concept_tags.json")


def _load_concept_tags_by_category() -> dict[str, list[str]]:
    """Load concept tags grouped by category from bundled JSON file."""
    with CONCEPT_TAGS_PATH.open(encoding="utf-8") as concept_tags_file:
        payload = json.load(concept_tags_file)
    tags = payload.get("tags", {})
    return {
        str(category): [str(tag) for tag in category_tags]
        for category, category_tags in tags.items()
        if isinstance(category_tags, list)
    }


CONCEPT_TAGS_BY_CATEGORY = _load_concept_tags_by_category()
ALLOWED_CONCEPT_CATEGORIES = set(get_args(ConceptTagCategory))


class RagTools:
    tools = [
        "search_knowledge_base",
        "expand_graph_by_ids",
        "get_entity_by_number",
        "get_related_code_definitions",
        "get_search_tags_catalog",
    ]

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
                    MetadataFilter(
                        field=metadata_field, operator=MetadataFilterOperator.EQ, value=value
                    )
                )

        if not metadata_filters:
            return None

        return MetadataFilters(filters=metadata_filters, condition="and")

    @staticmethod
    def _extract_search_tags(search_tags: SearchTags | None) -> SearchTags | None:
        """Normalize optional explicit search tags config."""
        if search_tags is None:
            return None
        if search_tags.bc_concepts or search_tags.bc_db_tables:
            return search_tags
        return None

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
        search_tags: Annotated[
            SearchTags | None,
            "Optional concept/table tags used for similarity boosting.",
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
            search_tags=search_tags.model_dump() if search_tags else None,
        )
        metadata_filters = self._convert_search_filters(filters)
        resolved_boosting = self._extract_search_tags(search_tags)
        booster = SearchResultBooster(resolved_boosting, k)
        candidate_k = booster.candidate_limit_for_boosting()

        root_documents = await self._repository.vector_search(
            query,
            candidate_k,
            metadata_filters,
        )
        boosted_roots = booster.apply(root_documents)

        expanded_documents: list[Document] = []
        if traverse_types:
            root_ids = [document.id for document in boosted_roots if document.id is not None]
            if root_ids:
                expanded_documents = await self._repository.expand_graph_by_ids(
                    root_ids,
                    traverse_types,
                )

        documents = SearchResultBooster.deduplicate_documents(boosted_roots + expanded_documents)
        logger.info(
            "rag tool result",
            tool="search_knowledge_base",
            num_documents=len(documents),
            num_root_documents=len(boosted_roots),
            num_expanded_documents=len(expanded_documents),
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
        chunk_type_value = ENTITY_TYPE_TO_CHUNK_TYPE.get(entity_type, entity_type.value)
        filters = MetadataFilters(
            filters=[
                MetadataFilter(
                    field="chunk_type", operator=MetadataFilterOperator.EQ, value=chunk_type_value
                ),
                MetadataFilter(field="entity_id", operator=MetadataFilterOperator.EQ, value=number),
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

    async def get_related_code_definitions(
        self,
        document_ids: Annotated[
            list[str],
            "Algorithm or example document IDs to retrieve related code definitions.",
        ],
    ) -> Document:
        """
        Retrieve related code definitions as one wrapped document.

        The returned document contains reconstructed source in ``content``.
        Unused fields may be ``null``.
        """
        logger.info(
            "rag tool call",
            tool="get_related_code_definitions",
            document_ids=document_ids,
        )
        document = await self._repository.get_related_code_definitions(document_ids)
        logger.info(
            "rag tool result",
            tool="get_related_code_definitions",
            content_len=len(document.content),
        )
        return document

    async def get_search_tags_catalog(
        self,
        tag_type: Annotated[
            Literal["concepts", "tables"],
            "Which tag list to return for search_tags: 'concepts' (bc_concepts) or "
            "'tables' (bc_db_tables).",
        ],
        category: Annotated[
            ConceptTagCategory | None,
            "Optional category filter for 'concepts' only; ignored for 'tables'.",
        ] = None,
    ) -> Document:
        """Use this tool to ground retrieval in the right domain vocabulary before searching.

        It is helpful to choose standardized tags that narrow search intent,
        reduce ambiguity, and improve relevance when querying the knowledge base.
        For `tag_type='concepts'`, if `category` is not provided, all concept tags are returned.
        """
        selected_category = category if tag_type == "concepts" else None
        payload_items: list[str]

        if tag_type == "concepts":
            if selected_category:
                payload_items = CONCEPT_TAGS_BY_CATEGORY[selected_category]
            else:
                payload_items = [
                    tag
                    for category_tags in CONCEPT_TAGS_BY_CATEGORY.values()
                    for tag in category_tags
                ]
        else:
            payload_items = SUPPORTED_DB_TABLES

        logger.info(
            "rag tool result",
            tool="get_search_tags_catalog",
            tag_type=tag_type,
            selected_category=selected_category,
            item_count=len(payload_items),
        )
        return Document(
            content=f"Available search_tags {tag_type}",
            metadata=SearchTagsCatalogMetadata(
                tag_type=tag_type,
                selected_category=selected_category,
                items=payload_items,
            ).model_dump(),
        )


def create_mcp_server(repository: AbstractVectorStoreRepository) -> FastMCP:
    """Create MCP server and register tools."""

    @lifespan
    async def server_lifespan(server: FastMCP) -> AsyncGenerator[None, None]:
        """Manage repository connection lifespan."""
        async with repository:
            yield

    mcp = FastMCP(
        "'Algorithms for Decision Making' book RAG",
        instructions="""
Book contents:
part number title
section_number title page
""" + BOOK_CONTENTS,
        lifespan=server_lifespan,
    )
    rag_tools = RagTools(repository)
    for tool_name in RagTools.tools:
        mcp.tool(getattr(rag_tools, tool_name))
    return mcp
