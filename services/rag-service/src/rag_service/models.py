"""
Data models for RAG service.

Contains document models, entity types, and filter structures used by both
the MCP tools layer and the repository layer.
"""

from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field


class EntityType(StrEnum):
    FORMULA = "formula"
    TABLE = "table"
    ALGORITHM = "algorithm"
    IMAGE = "image"
    EXERCISE = "exercise"
    EXAMPLE = "example"


Part = Literal["I", "II", "III", "IV", "V", "Appendices"]


class SearchFilters(BaseModel):
    """Tool-level filters for knowledge base search."""

    part: Part | None = None
    section: Annotated[str | None, Field(description="Section number e.g. 2")] = None
    subsection: Annotated[str | None, Field(description="Subsection number e.g. 2.3")] = None
    subsubsection: Annotated[str | None, Field(description="Subsubsection number e.g. 2.3.1")] = (
        None
    )
    page_number: int | None = None


class Document(BaseModel):
    """Document returned from vector store search."""

    id: str
    content: str
    cosine_similarity: float
    metadata: dict[str, Any]


class MetadataFilter(BaseModel):
    """
    Single metadata filter condition for repository queries.
    """

    field: str
    operator: Literal["eq", "in"]
    value: str | int | float | bool | list[str] | list[int] | list[float] | list[bool] | None


class MetadataFilters(BaseModel):
    """
    Container for multiple metadata filter conditions.

    Args:
        filters: List of individual filter conditions.
        condition: How to combine filters - "and" (all must match) or "or" (any can match).
    """

    filters: list[MetadataFilter] = Field(default_factory=list)
    condition: Literal["and", "or"] = Field(default="and")
