from typing import Any

from pydantic import BaseModel, Field


class AgentQueryRequest(BaseModel):
    """Request model for agent query"""

    query: str = Field(..., description="User query for the agent", min_length=1)
    context: dict[str, Any] | None = Field(
        default=None, description="Additional context for the query"
    )
    max_iterations: int | None = Field(
        default=10, description="Maximum number of ReAct iterations", ge=1, le=20
    )


class ToolExecutionRequest(BaseModel):
    """Request model for tool execution"""

    tool_name: str = Field(..., description="Name of the tool to execute")
    parameters: dict[str, Any] = Field(..., description="Tool parameters")
