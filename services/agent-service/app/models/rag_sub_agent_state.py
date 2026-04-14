from datetime import UTC, datetime
from typing import Annotated, Literal, TypedDict
from uuid import uuid4

from app.models.agent_state import ThoughtStep, ToolCall, merge_token_usage
from langchain_core.messages import AnyMessage
from langgraph.graph import add_messages


class RAGSubAgentState(TypedDict):
    """
    State for the ReAct agent loop.
    LangGraph will manage this state across iterations.
    """

    # Input
    request_id: str
    agent_query: str

    # Iteration tracking
    iteration: int
    max_iterations: int

    # Reasoning trace
    thoughts: list[ThoughtStep]
    tool_calls: list[ToolCall]
    messages: Annotated[list[AnyMessage], add_messages]
    final_chunks_ids: list[str] | None
    state_summary: str | None
    status: Literal["running", "completed", "failed"]
    error: str | None

    # Metadata
    token_usage: Annotated[dict[str, dict[str, int]], merge_token_usage]
    started_at: datetime
    completed_at: datetime | None


def create_initial_state(
    agent_query: str,
    max_iterations: int = 10,
) -> RAGSubAgentState:
    """Initialize agent state"""
    return RAGSubAgentState(
        request_id=str(uuid4()),
        agent_query=agent_query,
        iteration=0,
        max_iterations=max_iterations,
        thoughts=[],
        tool_calls=[],
        messages=[],
        final_chunks_ids=None,
        state_summary=None,
        status="running",
        error=None,
        token_usage={},
        started_at=datetime.now(UTC),
        completed_at=None,
    )
