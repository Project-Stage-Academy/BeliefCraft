from datetime import UTC, datetime
from typing import Any, Literal, TypedDict
from uuid import uuid4

from pydantic import BaseModel, Field


class ToolCall(BaseModel):
    """Represents a single tool invocation"""

    tool_name: str
    arguments: dict[str, Any]
    result: dict[str, Any] | None = None
    error: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ThoughtStep(BaseModel):
    """Represents a reasoning step"""

    thought: str
    reasoning: str | None = None
    next_action: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AgentState(TypedDict):
    """
    State for the ReAct agent loop.
    LangGraph will manage this state across iterations.
    """

    # Input
    request_id: str
    user_query: str
    context: dict[str, Any]

    # Iteration tracking
    iteration: int
    max_iterations: int

    # Reasoning trace
    thoughts: list[ThoughtStep]
    tool_calls: list[ToolCall]

    # LLM interaction
    messages: list[dict[str, Any]]  # Chat history for LLM

    # Output
    final_answer: str | None
    status: Literal["running", "completed", "failed", "max_iterations"]
    error: str | None

    # Metadata
    total_tokens: int
    started_at: datetime
    completed_at: datetime | None


def create_initial_state(
    user_query: str,
    context: dict[str, Any] | None = None,
    max_iterations: int = 10,
) -> AgentState:
    """Initialize agent state"""
    return AgentState(
        request_id=str(uuid4()),
        user_query=user_query,
        context=context or {},
        iteration=0,
        max_iterations=max_iterations,
        thoughts=[],
        tool_calls=[],
        messages=[],
        final_answer=None,
        status="running",
        error=None,
        total_tokens=0,
        started_at=datetime.now(UTC),
        completed_at=None,
    )
