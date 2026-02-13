from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


class AgentStep(BaseModel):
    """Single step in the agent's reasoning process"""

    step_number: int
    thought: str
    action: str
    action_input: dict[str, Any]
    observation: str


class AgentQueryResponse(BaseModel):
    """Response model for agent query"""

    request_id: str
    query: str
    status: str
    answer: str | None
    iterations: int
    total_tokens: int
    reasoning_trace: list[dict[str, Any]]
    duration_seconds: float


class ToolExecutionResponse(BaseModel):
    """Response model for tool execution"""

    tool_name: str
    result: Any
    execution_time_ms: float
    success: bool
    error: str | None = None


class ErrorResponse(BaseModel):
    """Error response model"""

    error: str
    message: str
    request_id: str | None = None
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
