from enum import StrEnum
from typing import Annotated, Literal

from common.logging import get_logger
from fastmcp import FastMCP
from pydantic import BaseModel, Field

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


class EntityType(StrEnum):
    FORMULA = "formula"
    TABLE = "table"
    ALGORITHM = "algorithm"
    IMAGE = "image"
    EXERCISE = "exercise"
    EXAMPLE = "example"


Part = Literal["I", "II", "III", "IV", "V", "Appendices"]


class SearchFilters(BaseModel):
    part: Part | None = None
    chapter: Annotated[str | None, Field(description="Chapter number e.g. 2")] = None
    subsection: Annotated[str | None, Field(description="Subsection number e.g. 2.3")] = None
    subsubsection: Annotated[str | None, Field(description="Subsubsection number e.g. 2.3.1")] = (
        None
    )
    page_number: int | None = None


class Document(BaseModel):
    id: str
    content: str
    cosine_similarity: float
    metadata: dict


class RagTools:
    tools = ["search_knowledge_base", "expand_graph_by_ids", "get_entity_by_number"]

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
        return []

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
        return []

    async def get_entity_by_number(
        self,
        entity_type: Annotated[EntityType, "Type of entity."],
        number: Annotated[str, "Unique number of the object, e.g., '1.2.4'."],
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
        return Document(id="mock", content="mock", metadata={}, cosine_similarity=1.0)


def create_mcp_server():
    """Create MCP server and register tools."""
    mcp = FastMCP(
        "'Algorithms for Decision Making' book RAG",
        instructions="""
Book contents:
part number title
section_number title page
""" + BOOK_CONTENTS,
    )
    rag_tools = RagTools()
    for tool_name in RagTools.tools:
        mcp.tool(getattr(rag_tools, tool_name))
    return mcp
