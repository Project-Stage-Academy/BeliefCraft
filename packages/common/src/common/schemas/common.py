from __future__ import annotations

from typing import Any, Generic, Self, TypeVar

from pydantic import BaseModel, ConfigDict, Field, model_validator

T = TypeVar("T")


class Pagination(BaseModel):
    """
    Shared pagination contract for Smart Query Builder requests.
    """

    limit: int = Field(default=50, ge=1, le=500)
    offset: int = Field(default=0, ge=0)

    model_config = ConfigDict(extra="forbid")


class ToolResultMeta(BaseModel):
    """
    Shared metadata contract for Smart Query Builder tool responses.

    Attributes:
        count: Generic count of primary items returned by the tool.
        trace_count: Optional count specifically intended for public reasoning traces.
        pagination: Optional pagination metadata for list-style responses.
    """

    count: int = Field(ge=0)
    trace_count: int | None = Field(default=None, ge=0)
    pagination: Pagination | None = None

    model_config = ConfigDict(extra="allow")

    @model_validator(mode="after")
    def default_trace_count(self) -> Self:
        if self.trace_count is None:
            self.trace_count = self.count
        return self


def build_tool_meta(
    *,
    count: int,
    trace_count: int | None = None,
    pagination: Pagination | None = None,
    **extra: Any,
) -> ToolResultMeta:
    """Create standardized tool metadata with optional extra fields."""
    return ToolResultMeta(
        count=count,
        trace_count=trace_count,
        pagination=pagination,
        **extra,
    )


class ToolResult(BaseModel, Generic[T]):
    """
    Standard envelope for tool responses returned to the agent layer.

    Metadata follows the shared ``ToolResultMeta`` contract.
    """

    data: T
    message: str = Field(min_length=1)
    meta: ToolResultMeta

    model_config = ConfigDict(extra="forbid")
