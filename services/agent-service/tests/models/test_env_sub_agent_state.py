from datetime import UTC, datetime
from uuid import UUID

from app.models.env_sub_agent_state import ReActState, create_initial_state


def test_create_initial_state_populates_defaults() -> None:
    before = datetime.now(UTC)
    state = create_initial_state(agent_query="Check inventory")
    after = datetime.now(UTC)

    assert state["agent_query"] == "Check inventory"
    assert state["messages"] == []
    assert state["state_summary"] is None
    assert state["status"] == "running"
    assert state["error"] is None
    assert state["step_count"] == 0
    assert state["token_usage"] == {}
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


def test_react_state_expected_keys() -> None:
    expected_keys = {
        "request_id",
        "agent_query",
        "messages",
        "state_summary",
        "status",
        "error",
        "step_count",
        "token_usage",
        "started_at",
        "completed_at",
    }
    assert set(ReActState.__annotations__) == expected_keys
