from datetime import UTC, datetime
from typing import Annotated, Literal, TypedDict
from uuid import uuid4

from app.models.agent_state import merge_token_usage
from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


class ReActState(TypedDict):
    request_id: str
    agent_query: str

    messages: Annotated[list[AnyMessage], add_messages]
    state_summary: str | None

    status: Literal["running", "completed", "failed"]
    error: str | None

    step_count: int  # Added to track iterations

    token_usage: Annotated[dict[str, dict[str, int]], merge_token_usage]
    started_at: datetime
    completed_at: datetime | None


def create_initial_state(
    agent_query: str,
) -> ReActState:
    return ReActState(
        request_id=str(uuid4()),
        agent_query=agent_query,
        messages=[],
        state_summary=None,
        status="running",
        error=None,
        step_count=0,  # Initialized to 0
        token_usage={},
        started_at=datetime.now(UTC),
        completed_at=None,
    )
