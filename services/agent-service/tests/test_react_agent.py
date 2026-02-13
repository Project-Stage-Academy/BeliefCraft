"""Tests for the ReAct agent state machine."""

import json
from collections.abc import Generator
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.models.agent_state import AgentState, create_initial_state
from app.services.react_agent import ReActAgent


def _make_llm_response(
    content: str = "test response",
    tool_calls: list[dict[str, Any]] | None = None,
    finish_reason: str = "stop",
    prompt_tokens: int = 10,
    completion_tokens: int = 20,
) -> dict[str, Any]:
    """Helper to create a mock LLM response dict."""
    return {
        "message": {"role": "assistant", "content": content},
        "tool_calls": tool_calls or [],
        "finish_reason": finish_reason,
        "tokens": {
            "prompt": prompt_tokens,
            "completion": completion_tokens,
            "total": prompt_tokens + completion_tokens,
        },
    }


@pytest.fixture()
def mock_llm_service() -> Generator[MagicMock, None, None]:
    """Create a mock LLMService that avoids real AWS connections."""
    with patch("app.services.react_agent.LLMService") as mock_cls:
        instance = MagicMock()
        instance.chat_completion = AsyncMock()
        mock_cls.return_value = instance
        yield instance


@pytest.fixture()
def agent(mock_llm_service: MagicMock) -> ReActAgent:
    """Create a ReActAgent with mocked LLM."""
    return ReActAgent()


@pytest.fixture()
def initial_state() -> AgentState:
    """Create a basic initial state for unit tests."""
    return create_initial_state(
        user_query="What is the current inventory level?",
        context={"warehouse_id": "WH-001"},
        max_iterations=5,
    )


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------


class TestBuildGraph:
    def test_graph_compiles(self, agent: ReActAgent) -> None:
        assert agent.graph is not None

    def test_agent_has_llm(self, agent: ReActAgent, mock_llm_service: MagicMock) -> None:
        assert agent.llm is mock_llm_service


# ---------------------------------------------------------------------------
# Think node
# ---------------------------------------------------------------------------


class TestThinkNode:
    @pytest.mark.asyncio()
    async def test_think_returns_thought_and_messages(
        self, agent: ReActAgent, mock_llm_service: MagicMock, initial_state: AgentState
    ) -> None:
        mock_llm_service.chat_completion.return_value = _make_llm_response(
            content="<thinking>Analyzing inventory...</thinking>",
            tool_calls=[
                {
                    "id": "tc_1",
                    "type": "function",
                    "function": {
                        "name": "get_inventory",
                        "arguments": '{"warehouse": "WH-001"}',
                    },
                }
            ],
            finish_reason="tool_calls",
        )

        result = await agent._think_node(initial_state)

        # One new assistant message appended
        assert len(result["messages"]) == 1
        assert result["messages"][0]["role"] == "assistant"

        # One new thought recorded
        assert len(result["thoughts"]) == 1
        assert result["thoughts"][0].next_action == "tool_use"

        # Tokens accumulated
        assert result["total_tokens"] == 30

        # No final answer when tool calls are pending
        assert "final_answer" not in result

    @pytest.mark.asyncio()
    async def test_think_detects_final_answer_marker(
        self, agent: ReActAgent, mock_llm_service: MagicMock, initial_state: AgentState
    ) -> None:
        mock_llm_service.chat_completion.return_value = _make_llm_response(
            content="FINAL ANSWER: The inventory level is 500 units.",
        )

        result = await agent._think_node(initial_state)

        assert result["final_answer"] == "The inventory level is 500 units."
        assert result["status"] == "completed"

    @pytest.mark.asyncio()
    async def test_think_treats_bare_stop_as_answer(
        self, agent: ReActAgent, mock_llm_service: MagicMock, initial_state: AgentState
    ) -> None:
        """When LLM stops without tools and without FINAL ANSWER tag,
        the full content is used as the answer."""
        mock_llm_service.chat_completion.return_value = _make_llm_response(
            content="The inventory is at healthy levels.",
        )

        result = await agent._think_node(initial_state)

        assert result["final_answer"] == "The inventory is at healthy levels."
        assert result["status"] == "completed"

    @pytest.mark.asyncio()
    async def test_think_stores_tool_calls_on_message(
        self, agent: ReActAgent, mock_llm_service: MagicMock, initial_state: AgentState
    ) -> None:
        tool_calls = [
            {
                "id": "tc_1",
                "type": "function",
                "function": {"name": "get_inventory", "arguments": "{}"},
            }
        ]
        mock_llm_service.chat_completion.return_value = _make_llm_response(
            content="Let me check...",
            tool_calls=tool_calls,
            finish_reason="tool_calls",
        )

        result = await agent._think_node(initial_state)
        last_msg = result["messages"][-1]

        assert last_msg["tool_calls"] == tool_calls

    @pytest.mark.asyncio()
    async def test_think_no_tool_calls_omits_key_on_message(
        self, agent: ReActAgent, mock_llm_service: MagicMock, initial_state: AgentState
    ) -> None:
        """When there are no tool calls, the assistant message should not
        carry an empty tool_calls list."""
        mock_llm_service.chat_completion.return_value = _make_llm_response(
            content="All done.",
        )

        result = await agent._think_node(initial_state)
        last_msg = result["messages"][-1]

        assert "tool_calls" not in last_msg

    @pytest.mark.asyncio()
    async def test_think_error_sets_failed_status(
        self, agent: ReActAgent, mock_llm_service: MagicMock, initial_state: AgentState
    ) -> None:
        mock_llm_service.chat_completion.side_effect = Exception("API timeout")

        result = await agent._think_node(initial_state)

        assert result["status"] == "failed"
        assert "API timeout" in result["error"]

    @pytest.mark.asyncio()
    async def test_think_accumulates_tokens(
        self, agent: ReActAgent, mock_llm_service: MagicMock, initial_state: AgentState
    ) -> None:
        initial_state["total_tokens"] = 50
        mock_llm_service.chat_completion.return_value = _make_llm_response(
            content="OK",
            prompt_tokens=20,
            completion_tokens=30,
        )

        result = await agent._think_node(initial_state)

        assert result["total_tokens"] == 100  # 50 + 50

    @pytest.mark.asyncio()
    async def test_think_extends_existing_messages(
        self, agent: ReActAgent, mock_llm_service: MagicMock, initial_state: AgentState
    ) -> None:
        """New assistant message is appended to the existing list, not replacing it."""
        initial_state["messages"] = [{"role": "user", "content": "Hi"}]
        mock_llm_service.chat_completion.return_value = _make_llm_response(
            content="Hello!",
        )

        result = await agent._think_node(initial_state)

        assert len(result["messages"]) == 2
        assert result["messages"][0]["role"] == "user"
        assert result["messages"][1]["role"] == "assistant"


# ---------------------------------------------------------------------------
# Act node
# ---------------------------------------------------------------------------


class TestActNode:
    def test_act_executes_tool_calls(self, agent: ReActAgent, initial_state: AgentState) -> None:
        initial_state["messages"] = [
            {
                "role": "assistant",
                "content": "Checking...",
                "tool_calls": [
                    {
                        "id": "tc_1",
                        "type": "function",
                        "function": {
                            "name": "get_inventory",
                            "arguments": '{"warehouse": "WH-001"}',
                        },
                    }
                ],
            }
        ]

        result = agent._act_node(initial_state)

        assert len(result["tool_calls"]) == 1
        assert result["tool_calls"][0].tool_name == "get_inventory"
        assert result["tool_calls"][0].arguments == {"warehouse": "WH-001"}
        assert result["tool_calls"][0].result is not None
        assert result["iteration"] == 1

    def test_act_adds_tool_result_message(
        self, agent: ReActAgent, initial_state: AgentState
    ) -> None:
        initial_state["messages"] = [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "tc_1",
                        "type": "function",
                        "function": {"name": "get_inventory", "arguments": "{}"},
                    }
                ],
            }
        ]

        result = agent._act_node(initial_state)

        tool_msgs = [m for m in result["messages"] if m["role"] == "tool"]
        assert len(tool_msgs) == 1
        assert tool_msgs[0]["tool_call_id"] == "tc_1"
        assert tool_msgs[0]["name"] == "get_inventory"

    def test_act_handles_tool_error(self, agent: ReActAgent, initial_state: AgentState) -> None:
        agent._execute_tool = MagicMock(side_effect=Exception("Connection refused"))  # type: ignore[method-assign]

        initial_state["messages"] = [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "tc_1",
                        "type": "function",
                        "function": {"name": "broken_tool", "arguments": "{}"},
                    }
                ],
            }
        ]

        result = agent._act_node(initial_state)

        assert result["tool_calls"][0].error is not None
        assert "Connection refused" in result["tool_calls"][0].error

        # Error tool message is still sent so LLM can reason about it
        tool_msgs = [m for m in result["messages"] if m["role"] == "tool"]
        assert len(tool_msgs) == 1
        assert "error" in json.loads(tool_msgs[0]["content"])

    def test_act_handles_multiple_tool_calls(
        self, agent: ReActAgent, initial_state: AgentState
    ) -> None:
        initial_state["messages"] = [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "tc_1",
                        "type": "function",
                        "function": {"name": "tool_a", "arguments": "{}"},
                    },
                    {
                        "id": "tc_2",
                        "type": "function",
                        "function": {
                            "name": "tool_b",
                            "arguments": '{"key": "val"}',
                        },
                    },
                ],
            }
        ]

        result = agent._act_node(initial_state)

        assert len(result["tool_calls"]) == 2
        tool_msgs = [m for m in result["messages"] if m["role"] == "tool"]
        assert len(tool_msgs) == 2

    def test_act_no_tool_calls_in_message(
        self, agent: ReActAgent, initial_state: AgentState
    ) -> None:
        """Act node handles messages without tool_calls gracefully."""
        initial_state["messages"] = [{"role": "assistant", "content": "No tools needed."}]

        result = agent._act_node(initial_state)

        assert len(result["tool_calls"]) == 0
        assert result["iteration"] == 1

    def test_act_increments_iteration(self, agent: ReActAgent, initial_state: AgentState) -> None:
        initial_state["iteration"] = 3
        initial_state["messages"] = [{"role": "assistant", "content": "done"}]

        result = agent._act_node(initial_state)

        assert result["iteration"] == 4

    def test_act_preserves_existing_messages(
        self, agent: ReActAgent, initial_state: AgentState
    ) -> None:
        initial_state["messages"] = [
            {"role": "user", "content": "query"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "tc_1",
                        "type": "function",
                        "function": {"name": "t", "arguments": "{}"},
                    }
                ],
            },
        ]

        result = agent._act_node(initial_state)

        # Original 2 messages + 1 new tool result
        assert len(result["messages"]) == 3
        assert result["messages"][0]["role"] == "user"
        assert result["messages"][1]["role"] == "assistant"
        assert result["messages"][2]["role"] == "tool"


# ---------------------------------------------------------------------------
# Parse tool arguments
# ---------------------------------------------------------------------------


class TestParseToolArguments:
    def test_parse_valid_json_string(self) -> None:
        result = ReActAgent._parse_tool_arguments('{"key": "value"}')
        assert result == {"key": "value"}

    def test_parse_dict_passthrough(self) -> None:
        result = ReActAgent._parse_tool_arguments({"key": "value"})
        assert result == {"key": "value"}

    def test_parse_malformed_json_fallback(self) -> None:
        result = ReActAgent._parse_tool_arguments("not valid json")
        assert result == {"query": "not valid json"}

    def test_parse_empty_string(self) -> None:
        result = ReActAgent._parse_tool_arguments("")
        assert result == {"query": ""}

    def test_parse_nested_json(self) -> None:
        raw = '{"filters": {"status": "active"}, "limit": 10}'
        result = ReActAgent._parse_tool_arguments(raw)
        assert result == {"filters": {"status": "active"}, "limit": 10}


# ---------------------------------------------------------------------------
# Routing logic
# ---------------------------------------------------------------------------


class TestShouldContinue:
    def test_continue_when_running(self, agent: ReActAgent, initial_state: AgentState) -> None:
        result = agent._should_continue(initial_state)
        assert result == "continue"

    def test_finalize_when_completed(self, agent: ReActAgent, initial_state: AgentState) -> None:
        initial_state["status"] = "completed"
        assert agent._should_continue(initial_state) == "finalize"

    def test_finalize_when_failed(self, agent: ReActAgent, initial_state: AgentState) -> None:
        initial_state["status"] = "failed"
        assert agent._should_continue(initial_state) == "finalize"

    def test_finalize_when_has_final_answer(
        self, agent: ReActAgent, initial_state: AgentState
    ) -> None:
        initial_state["final_answer"] = "The answer is 42."
        assert agent._should_continue(initial_state) == "finalize"

    def test_max_iterations_at_limit(self, agent: ReActAgent, initial_state: AgentState) -> None:
        initial_state["iteration"] = 5  # equals max_iterations
        assert agent._should_continue(initial_state) == "max_iterations"

    def test_max_iterations_over_limit(self, agent: ReActAgent, initial_state: AgentState) -> None:
        initial_state["iteration"] = 10
        assert agent._should_continue(initial_state) == "max_iterations"

    def test_continue_one_below_limit(self, agent: ReActAgent, initial_state: AgentState) -> None:
        initial_state["iteration"] = 4  # one below max_iterations=5
        assert agent._should_continue(initial_state) == "continue"

    def test_does_not_mutate_state(self, agent: ReActAgent, initial_state: AgentState) -> None:
        """Routing function must be pure — no side effects on state."""
        initial_state["iteration"] = 5
        original_status = initial_state["status"]

        agent._should_continue(initial_state)

        assert initial_state["status"] == original_status


# ---------------------------------------------------------------------------
# Finalize node
# ---------------------------------------------------------------------------


class TestFinalizeNode:
    def test_finalize_sets_completed_at(self, agent: ReActAgent, initial_state: AgentState) -> None:
        initial_state["status"] = "completed"
        initial_state["final_answer"] = "Done."

        result = agent._finalize_node(initial_state)

        assert isinstance(result["completed_at"], datetime)

    def test_finalize_max_iterations_provides_fallback(
        self, agent: ReActAgent, initial_state: AgentState
    ) -> None:
        initial_state["iteration"] = 5  # equals max
        initial_state["final_answer"] = None

        result = agent._finalize_node(initial_state)

        assert result["status"] == "max_iterations"
        assert "iteration limit" in result["final_answer"]

    def test_finalize_marks_running_as_completed(
        self, agent: ReActAgent, initial_state: AgentState
    ) -> None:
        initial_state["status"] = "running"
        initial_state["final_answer"] = "Here is the answer."

        result = agent._finalize_node(initial_state)

        assert result["status"] == "completed"

    def test_finalize_preserves_failed_status(
        self, agent: ReActAgent, initial_state: AgentState
    ) -> None:
        initial_state["status"] = "failed"
        initial_state["error"] = "Something broke"

        result = agent._finalize_node(initial_state)

        assert "status" not in result

    def test_finalize_max_iterations_with_existing_answer(
        self, agent: ReActAgent, initial_state: AgentState
    ) -> None:
        """If the agent already has a final answer at max iterations,
        do not override it with the fallback message."""
        initial_state["iteration"] = 5
        initial_state["final_answer"] = "Partial but valid answer."

        result = agent._finalize_node(initial_state)

        # Should NOT override existing answer
        assert "final_answer" not in result or (
            result.get("final_answer") == "Partial but valid answer."
        )


# ---------------------------------------------------------------------------
# Tool stubs
# ---------------------------------------------------------------------------


class TestToolStubs:
    def test_execute_tool_returns_stub(self, agent: ReActAgent) -> None:
        result = agent._execute_tool("any_tool", {"key": "value"})
        assert result["status"] == "stub"
        assert "any_tool" in result["message"]

    def test_get_tool_definitions_returns_empty(self, agent: ReActAgent) -> None:
        assert agent._get_tool_definitions() == []


# ---------------------------------------------------------------------------
# Full run integration
# ---------------------------------------------------------------------------


class TestRun:
    @pytest.mark.asyncio()
    async def test_run_direct_answer(self, agent: ReActAgent, mock_llm_service: MagicMock) -> None:
        mock_llm_service.chat_completion.return_value = _make_llm_response(
            content="FINAL ANSWER: Inventory is at 500 units.",
        )

        result = await agent.run("What is the inventory?")

        assert result["status"] == "completed"
        assert result["final_answer"] is not None
        assert "500 units" in result["final_answer"]
        assert result["completed_at"] is not None

    @pytest.mark.asyncio()
    async def test_run_with_tool_use_loop(
        self, agent: ReActAgent, mock_llm_service: MagicMock
    ) -> None:
        """Agent performs one tool-use cycle then gives final answer."""
        mock_llm_service.chat_completion.side_effect = [
            _make_llm_response(
                content="Let me check inventory.",
                tool_calls=[
                    {
                        "id": "tc_1",
                        "type": "function",
                        "function": {
                            "name": "get_inventory",
                            "arguments": "{}",
                        },
                    }
                ],
                finish_reason="tool_calls",
            ),
            _make_llm_response(
                content="FINAL ANSWER: Inventory is at 500 units.",
            ),
        ]

        result = await agent.run("What is the inventory?")

        assert result["status"] == "completed"
        assert result["iteration"] == 1
        assert len(result["tool_calls"]) == 1
        assert len(result["thoughts"]) == 2
        assert mock_llm_service.chat_completion.call_count == 2

    @pytest.mark.asyncio()
    async def test_run_max_iterations(self, agent: ReActAgent, mock_llm_service: MagicMock) -> None:
        """Agent stops after hitting the iteration limit."""
        mock_llm_service.chat_completion.return_value = _make_llm_response(
            content="Need more data...",
            tool_calls=[
                {
                    "id": "tc_1",
                    "type": "function",
                    "function": {"name": "get_data", "arguments": "{}"},
                }
            ],
            finish_reason="tool_calls",
        )

        result = await agent.run("Complex query", max_iterations=2)

        assert result["status"] == "max_iterations"
        assert result["final_answer"] is not None
        assert "iteration limit" in result["final_answer"]
        # 3 think calls: iteration 0, 1, then 2 (hits limit after think)
        assert mock_llm_service.chat_completion.call_count == 3

    @pytest.mark.asyncio()
    async def test_run_passes_context(self, agent: ReActAgent, mock_llm_service: MagicMock) -> None:
        mock_llm_service.chat_completion.return_value = _make_llm_response(
            content="FINAL ANSWER: Done.",
        )

        result = await agent.run(
            "Check warehouse",
            context={"warehouse_id": "WH-001"},
            max_iterations=3,
        )

        assert result["context"] == {"warehouse_id": "WH-001"}
        assert result["max_iterations"] == 3

    @pytest.mark.asyncio()
    async def test_run_llm_error_produces_failed_state(
        self, agent: ReActAgent, mock_llm_service: MagicMock
    ) -> None:
        """LLM errors are caught in the think node, producing a failed state
        rather than raising out of run()."""
        mock_llm_service.chat_completion.side_effect = Exception("Service unavailable")

        result = await agent.run("What is inventory?")

        assert result["status"] == "failed"
        assert result["error"] is not None

    @pytest.mark.asyncio()
    async def test_run_sets_request_id(
        self, agent: ReActAgent, mock_llm_service: MagicMock
    ) -> None:
        mock_llm_service.chat_completion.return_value = _make_llm_response(
            content="FINAL ANSWER: Done.",
        )

        result = await agent.run("test query")

        assert result["request_id"] is not None
        assert len(result["request_id"]) > 0

    @pytest.mark.asyncio()
    async def test_run_records_started_at(
        self, agent: ReActAgent, mock_llm_service: MagicMock
    ) -> None:
        mock_llm_service.chat_completion.return_value = _make_llm_response(
            content="FINAL ANSWER: Done.",
        )

        before = datetime.now(UTC)
        result = await agent.run("test query")
        after = datetime.now(UTC)

        assert before <= result["started_at"] <= after
