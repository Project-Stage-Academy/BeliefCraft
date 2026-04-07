"""Tools API endpoints."""

from typing import Any

from common.logging import get_logger
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

logger = get_logger(__name__)

router = APIRouter()


class ToolInfo(BaseModel):
    name: str = Field(..., description="Tool name")
    description: str = Field(..., description="Tool description")
    category: str = Field(..., description="Tool category (environment/rag/planning/utility/skill)")
    parameters: dict[str, Any] = Field(..., description="Tool parameter schema")


class ToolListResponse(BaseModel):
    tools: list[ToolInfo] = Field(..., description="List of available tools")
    total_count: int = Field(..., description="Total number of tools returned")


@router.get("/tools", response_model=ToolListResponse)
async def list_tools(
    request: Request,
    category: str | None = Query(
        None,
        description="Filter by category (environment, rag, planning, utility, skill)",
        pattern="^(environment|rag|planning|utility|skill|mcp)$",
    ),
) -> ToolListResponse:
    try:
        react_registry = getattr(request.app.state, "react_agent_registry", None)
        env_registry = getattr(request.app.state, "env_sub_agent_registry", None)

        if not react_registry and not env_registry:
            raise ValueError("No tool registries initialized in app state")

        all_tools = {}

        if react_registry:
            for tool in react_registry.list_tools(category=category):
                all_tools[tool.metadata.name] = tool

        if env_registry:
            for tool in env_registry.list_tools(category=category):
                all_tools[tool.metadata.name] = tool

        tools = list(all_tools.values())

    except Exception as e:
        logger.error("tool_registry_list_failed", category=category, error=str(e))
        raise HTTPException(status_code=500, detail="Failed to retrieve tools from registry") from e

    tool_infos = [
        ToolInfo(
            name=tool.metadata.name,
            description=tool.metadata.description,
            category=tool.metadata.category,
            parameters=tool.metadata.parameters,
        )
        for tool in tools
    ]

    return ToolListResponse(
        tools=tool_infos,
        total_count=len(tool_infos),
    )
