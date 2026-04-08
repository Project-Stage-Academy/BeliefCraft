from datetime import UTC, datetime
from uuid import UUID

from app.models.env_sub_agent_state import ReWOOState, create_initial_state


def test_create_initial_state_populates_defaults() -> None:
    before = datetime.now(UTC)
    state = create_initial_state(agent_query="Check inventory")
    after = datetime.now(UTC)

    assert state["agent_query"] == "Check inventory"
    assert state["plan"] is None
    assert state["observations"] == {}
    assert state["state_summary"] is None
    assert state["status"] == "planning"
    assert state["error"] is None
    assert state["total_tokens"] == 0
    assert before <= state["started_at"] <= after
    assert state["completed_at"] is None


def test_create_initial_state_generates_valid_uuid() -> None:
    state = create_initial_state(agent_query="test")

    parsed_uuid = UUID(state["request_id"])
    assert str(parsed_uuid) == state["request_id"]


def test_create_initial_state_generates_unique_ids() -> None:
    state1 = create_initial_state(agent_query="test1")
    state2 = create_initial_state(agent_query="test2")

    assert state1["request_id"] != state2["request_id"]


def test_rewoo_state_expected_keys() -> None:
    expected_keys = {
        "request_id",
        "agent_query",
        "plan",
        "observations",
        "state_summary",
        "status",
        "error",
        "total_tokens",
        "started_at",
        "completed_at",
    }
    assert set(ReWOOState.__annotations__) == expected_keys
