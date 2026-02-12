from pydantic import BaseModel, Field
from typing import Optional, Dict, Any


class AgentQueryRequest(BaseModel):
    """Request model for agent query"""
    query: str = Field(..., description="User query for the agent", min_length=1)
    context: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Additional context for the query"
    )
    max_iterations: Optional[int] = Field(
        default=10,
        description="Maximum number of ReAct iterations",
        ge=1,
        le=20
    )


class ToolExecutionRequest(BaseModel):
    """Request model for tool execution"""
    tool_name: str = Field(..., description="Name of the tool to execute")
    parameters: Dict[str, Any] = Field(..., description="Tool parameters")
