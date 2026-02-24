from __future__ import annotations

from collections.abc import Callable
from typing import Any

from common.schemas.common import ToolResult
from fastapi import HTTPException, status
from pydantic import ValidationError


def execute_tool(tool_call: Callable[[], ToolResult[Any]]) -> dict[str, Any]:
    try:
        result = tool_call()
        return result.model_dump(mode="json")
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=exc.errors(),
        ) from exc
    except RuntimeError as exc:
        if isinstance(exc.__cause__, ValueError):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(exc.__cause__),
            ) from exc
        if isinstance(exc.__cause__, ValidationError):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=exc.__cause__.errors(),
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to process smart query request.",
        ) from exc
