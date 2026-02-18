"""Tools API endpoints."""

from typing import Any

from app.tools.registry import tool_registry
from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

router = APIRouter()


class ToolInfo(BaseModel):
    """Information about a single tool."""

    name: str = Field(..., description="Tool name")
    description: str = Field(..., description="Tool description")
    category: str = Field(..., description="Tool category (environment/rag/planning/utility)")
    parameters: dict[str, Any] = Field(..., description="Tool parameter schema")


class ToolListResponse(BaseModel):
    """Response model for tools listing."""

    tools: list[ToolInfo] = Field(..., description="List of available tools")
    total_count: int = Field(..., description="Total number of tools returned")


@router.get("/tools", response_model=ToolListResponse)
async def list_tools(
    category: str | None = Query(
        None,
        description="Filter by category (environment, rag, planning, utility)",
    )
) -> ToolListResponse:
    """
    List all available tools for the agent.

    This endpoint returns metadata about all registered tools,
    optionally filtered by category. The schema format is compatible
    with OpenAI function calling and AWS Bedrock Claude function calling.

    Query parameters:
    - category: Optional filter by tool category

    Returns:
    - List of tools with their metadata and parameter schemas
    """
    tools = tool_registry.list_tools(category=category)

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
