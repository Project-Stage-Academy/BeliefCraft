from datetime import UTC, datetime

from app.models.agent_state import (
    AgentState,
    ThoughtStep,
    ToolCall,
    create_initial_state,
)


class TestToolCall:
    def test_minimal_tool_call(self) -> None:
        tc = ToolCall(tool_name="search", arguments={"query": "test"})
        assert tc.tool_name == "search"
        assert tc.arguments == {"query": "test"}
        assert tc.result is None
        assert tc.error is None
        assert tc.timestamp.tzinfo is not None

    def test_tool_call_with_result(self) -> None:
        tc = ToolCall(
            tool_name="search",
            arguments={"query": "test"},
            result={"items": [1, 2, 3]},
        )
        assert tc.result == {"items": [1, 2, 3]}
        assert tc.error is None

    def test_tool_call_with_error(self) -> None:
        tc = ToolCall(
            tool_name="search",
            arguments={"query": "test"},
            error="Connection timeout",
        )
        assert tc.result is None
        assert tc.error == "Connection timeout"

    def test_tool_call_timestamp_is_recent(self) -> None:
        before = datetime.now(UTC)
        tc = ToolCall(tool_name="search", arguments={})
        after = datetime.now(UTC)
        assert before <= tc.timestamp <= after


class TestThoughtStep:
    def test_thought_step_creation(self) -> None:
        step = ThoughtStep(
            thought="I need to search for data",
            reasoning="The user asked about inventory levels",
            next_action="call_search_tool",
        )
        assert step.thought == "I need to search for data"
        assert step.reasoning == "The user asked about inventory levels"
        assert step.next_action == "call_search_tool"
        assert step.timestamp.tzinfo is not None

    def test_thought_step_timestamp_is_recent(self) -> None:
        before = datetime.now(UTC)
        step = ThoughtStep(thought="t", reasoning="r", next_action="a")
        after = datetime.now(UTC)
        assert before <= step.timestamp <= after

    def test_thought_step_reasoning_defaults_to_none(self) -> None:
        step = ThoughtStep(thought="thinking", next_action="tool_use")
        assert step.reasoning is None


class TestCreateInitialState:
    def test_minimal_state(self) -> None:
        state = create_initial_state(user_query="What is the stock level?")
        assert state["user_query"] == "What is the stock level?"
        assert state["context"] == {}
        assert state["max_iterations"] == 10
        assert state["iteration"] == 0
        assert state["thoughts"] == []
        assert state["tool_calls"] == []
        assert state["messages"] == []
        assert state["final_answer"] is None
        assert state["status"] == "running"
        assert state["error"] is None
        assert state["total_tokens"] == 0
        assert state["completed_at"] is None

    def test_state_with_context(self) -> None:
        ctx = {"warehouse_id": "WH-001", "priority": "high"}
        state = create_initial_state(user_query="Check stock", context=ctx)
        assert state["context"] == ctx

    def test_state_with_custom_max_iterations(self) -> None:
        state = create_initial_state(user_query="Query", max_iterations=5)
        assert state["max_iterations"] == 5

    def test_request_id_is_uuid(self) -> None:
        from uuid import UUID

        state = create_initial_state(user_query="Query")
        UUID(state["request_id"])  # Raises ValueError if not valid UUID

    def test_request_id_is_unique(self) -> None:
        state1 = create_initial_state(user_query="Q1")
        state2 = create_initial_state(user_query="Q2")
        assert state1["request_id"] != state2["request_id"]

    def test_started_at_is_set(self) -> None:
        before = datetime.now(UTC)
        state = create_initial_state(user_query="Query")
        after = datetime.now(UTC)
        assert before <= state["started_at"] <= after

    def test_none_context_defaults_to_empty_dict(self) -> None:
        state = create_initial_state(user_query="Query", context=None)
        assert state["context"] == {}

    def test_state_is_typed_dict(self) -> None:
        state = create_initial_state(user_query="Query")
        assert isinstance(state, dict)


class TestAgentStateTypeStructure:
    """Verify AgentState has the expected keys via annotations."""

    def test_expected_keys(self) -> None:
        expected_keys = {
            "request_id",
            "user_query",
            "context",
            "iteration",
            "max_iterations",
            "thoughts",
            "tool_calls",
            "messages",
            "final_answer",
            "status",
            "error",
            "total_tokens",
            "started_at",
            "completed_at",
        }
        assert set(AgentState.__annotations__) == expected_keys
