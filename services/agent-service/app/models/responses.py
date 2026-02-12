from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone


class AgentStep(BaseModel):
    """Single step in the agent's reasoning process"""
    step_number: int
    thought: str
    action: str
    action_input: Dict[str, Any]
    observation: str


class AgentQueryResponse(BaseModel):
    """Response model for agent query"""
    request_id: str
    answer: str
    reasoning_steps: List[AgentStep]
    total_iterations: int
    execution_time_ms: float
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ToolExecutionResponse(BaseModel):
    """Response model for tool execution"""
    tool_name: str
    result: Any
    execution_time_ms: float
    success: bool
    error: Optional[str] = None


class ErrorResponse(BaseModel):
    """Error response model"""
    error: str
    message: str
    request_id: Optional[str] = None
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
