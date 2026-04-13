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

ConceptTagCategory = Literal[
    "POMDP_AND_BELIEF",
    "REINFORCEMENT_LEARNING",
    "PLANNING_AND_SEARCH",
    "PROBABILISTIC_INFERENCE",
    "RISK_AND_ROBUSTNESS",
    "MULTI_AGENT_AND_SUPPLY_CHAIN",
]


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

    id: str | None = None
    content: str
    cosine_similarity: float | None = None
    metadata: dict[str, Any] | None = None


class MetadataFilterOperator(StrEnum):
    EQ = "eq"
    IN = "in"


class MetadataFilter(BaseModel):
    """
    Single metadata filter condition for repository queries.
    """

    field: str
    operator: MetadataFilterOperator
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


class SearchTags(BaseModel):
    """Optional metadata tags used to boost semantically matched chunks."""

    bc_concepts: list[str] = Field(default_factory=list)
    bc_db_tables: list[str] = Field(default_factory=list)


class MissingEntityMetadata(BaseModel):
    """Metadata payload for entity lookups that miss."""

    found: Literal[False] = False
    entity_type: str
    number: str


class SearchTagsCatalogMetadata(BaseModel):
    """Metadata payload for search tag catalog responses."""

    tag_type: Literal["concepts", "tables"]
    selected_category: str | None = None
    items: list[str] = Field(default_factory=list)


SUPPORTED_DB_TABLES = [
    "warehouses",
    "suppliers",
    "leadtime_models",
    "routes",
    "shipments",
    "products",
    "locations",
    "inventory_balances",
    "inventory_moves",
    "orders",
    "order_lines",
    "purchase_orders",
    "po_lines",
    "sensor_devices",
    "observations",
]
