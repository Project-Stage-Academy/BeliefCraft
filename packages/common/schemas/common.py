from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class Pagination(BaseModel):
    """
    Shared pagination contract for Smart Query Builder requests.
    """

    limit: int = Field(default=50, ge=1, le=500)
    offset: int = Field(default=0, ge=0)

    model_config = ConfigDict(extra="forbid")


class ToolResult(BaseModel, Generic[T]):
    """
    Standard envelope for tool responses returned to the agent layer.
    """

    data: T
    message: str = Field(min_length=1)
    meta: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")
