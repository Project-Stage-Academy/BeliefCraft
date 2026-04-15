from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from common.schemas.common import ToolResult
from fastapi import HTTPException, status
from pydantic import ValidationError


def enum_value_or_raw(value: Any) -> Any:
    return getattr(value, "value", value)


def enum_values_or_none(values: Sequence[Any] | None) -> list[Any] | None:
    if not values:
        return None
    return [enum_value_or_raw(value) for value in values]


def execute_tool(tool_call: Callable[[], ToolResult[Any]]) -> dict[str, Any]:
    try:
        result = tool_call()
        return result.model_dump(mode="json")
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=exc.errors(),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except HTTPException:
        raise
    except RuntimeError as exc:
        cause = exc.__cause__

        if isinstance(cause, HTTPException):
            raise cause from exc
        if isinstance(cause, ValidationError):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=cause.errors(),
            ) from exc
        if isinstance(cause, ValueError):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(cause),
            ) from exc

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to process smart query request.",
        ) from exc
