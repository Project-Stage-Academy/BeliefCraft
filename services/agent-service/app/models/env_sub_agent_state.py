import operator
from datetime import UTC, datetime
from typing import Annotated, Any, Literal, TypedDict
from uuid import uuid4

from app.models.env_sub_agent_plans import WarehousePlan


class ReWOOState(TypedDict):
    """State for the Environment Sub-agent (ReWOO pattern)."""

    # 1. Input
    request_id: str
    agent_query: str

    # 2. Planner Output
    plan: WarehousePlan | None

    # 3. Executor Output
    observations: Annotated[
        dict[str, Any], operator.ior
    ]  # Maps tool execution names/IDs to raw JSON results

    # 4. Solver Output
    state_summary: str | None  # The final factual brief sent back to Main Agent

    # Execution Metadata
    status: Literal["planning", "executing", "solving", "completed", "failed"]
    error: str | None

    # Metadata
    total_tokens: Annotated[int, operator.add]
    started_at: datetime
    completed_at: datetime | None


def create_initial_state(
    agent_query: str,
) -> ReWOOState:
    """Initialize agent state"""
    return ReWOOState(
        request_id=str(uuid4()),
        agent_query=agent_query,
        plan=None,
        observations={},
        state_summary=None,
        status="planning",
        error=None,
        total_tokens=0,
        started_at=datetime.now(UTC),
        completed_at=None,
    )
