"""Tests for the ReAct agent state machine."""

import json
from collections.abc import Generator
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.models.agent_state import AgentState, create_initial_state
from app.services.react_agent import ReActAgent
from app.tools.factory import ToolRegistryFactory
from langchain_core.messages import AIMessage, HumanMessage


def _make_llm_response(
    content: str = "test response",
    tool_calls: list[dict[str, Any]] | None = None,
    finish_reason: str = "stop",
    model_id: str = "test-model",
    prompt_tokens: int = 10,
    completion_tokens: int = 20,
    cache_creation_input_tokens: int = 0,
    cache_read_input_tokens: int = 0,
) -> dict[str, Any]:
    """Helper to create a mock LLM response dict."""
    return {
        "message": {"role": "assistant", "content": content},
        "model_id": model_id,
        "tool_calls": tool_calls or [],
        "finish_reason": finish_reason,
        "tokens": {
            "prompt": prompt_tokens,
            "completion": completion_tokens,
            "cache_creation_input_tokens": cache_creation_input_tokens,
            "cache_read_input_tokens": cache_read_input_tokens,
            "total": prompt_tokens + completion_tokens,
        },
    }


@pytest.fixture()
def mock_llm_service() -> Generator[MagicMock, None, None]:
    """Create a mock LLMService that avoids real AWS connections."""
    with patch("app.services.base_agent.LLMService") as mock_cls:
        instance = MagicMock()
        instance.chat_completion = AsyncMock()
        mock_cls.return_value = instance
        yield instance


@pytest.fixture()
def agent(mock_llm_service: MagicMock) -> ReActAgent:
    """Create a ReActAgent with mocked LLM."""
    tool_registry = ToolRegistryFactory.create_react_agent_registry()
    return ReActAgent(tool_registry=tool_registry)


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

    def test_count_tool_executions_uses_messages_not_flat_state(self, agent: ReActAgent) -> None:
        messages = [
            AIMessage(
                content="",
                tool_calls=[{"id": "tc_1", "name": "get_inventory", "args": {}}],
            ),
            AIMessage(
                content="",
                tool_calls=[{"id": "tc_2", "name": "search_knowledge_base", "args": {}}],
            ),
        ]

        assert agent._count_tool_executions(messages) == 2


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

        # One new assistant message appended as an AIMessage object
        assert len(result["messages"]) == 1
        assert isinstance(result["messages"][0], AIMessage)
        assert result["messages"][0].tool_calls[0]["name"] == "get_inventory"

        # One new thought recorded
        assert len(result["thoughts"]) == 1
        assert result["thoughts"][0].next_action == "tool_use"

        # Tokens accumulated (returns delta)
        assert result["token_usage"]["test-model"]["total"] == 30

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
    async def test_think_no_tool_calls_omits_key_on_message(
        self, agent: ReActAgent, mock_llm_service: MagicMock, initial_state: AgentState
    ) -> None:
        """When there are no tool calls, the AIMessage should have an empty tool_calls list."""
        mock_llm_service.chat_completion.return_value = _make_llm_response(
            content="All done.",
        )

        result = await agent._think_node(initial_state)
        last_msg = result["messages"][-1]

        assert not last_msg.tool_calls

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
        mock_llm_service.chat_completion.return_value = _make_llm_response(
            content="OK",
            prompt_tokens=20,
            completion_tokens=30,
        )

        result = await agent._think_node(initial_state)

        assert result["token_usage"]["test-model"]["total"] == 50  # returns delta

    @pytest.mark.asyncio()
    async def test_think_extends_existing_messages(
        self, agent: ReActAgent, mock_llm_service: MagicMock, initial_state: AgentState
    ) -> None:
        """New assistant message is appended to the existing list, not replacing it."""
        initial_state["messages"] = [HumanMessage(content="Hi")]
        mock_llm_service.chat_completion.return_value = _make_llm_response(
            content="Hello!",
        )

        result = await agent._think_node(initial_state)

        assert (
            len(result["messages"]) == 1
        )  # LangGraph reducers handle the appending, so node just returns the new message
        assert isinstance(result["messages"][0], AIMessage)


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

        # Since we use native ToolNode, if the LLM hallucinated a tool not in lc_tools,
        # ToolNode automatically returns a ToolMessage with an error string and the loop continues,
        # perfectly matching our chat_completion side effects.
        result = await agent.run("What is the inventory?")

        assert result["status"] == "completed"
        assert result["iteration"] == 2
        assert len(result["thoughts"]) == 2
        assert mock_llm_service.chat_completion.call_count == 2

    @pytest.mark.asyncio()
    async def test_run_uses_env_sub_agent_facade_and_receives_summary(
        self, mock_llm_service: MagicMock
    ) -> None:
        mock_env_tool = MagicMock()
        mock_env_tool.metadata.name = "list_inventory_moves"

        env_registry = MagicMock()
        env_registry.list_tools.return_value = [mock_env_tool]

        tool_registry = ToolRegistryFactory.create_react_agent_registry(
            env_sub_registry=env_registry
        )
        agent = ReActAgent(tool_registry=tool_registry)

        assert sorted(agent.tool_registry.tools) == ["call_env_sub_agent", "python_sandbox"]
        assert "list_inventory_moves" not in agent.tool_registry.tools

        mock_llm_service.chat_completion.side_effect = [
            _make_llm_response(
                content="I need environment facts before answering.",
                tool_calls=[
                    {
                        "id": "tc_1",
                        "type": "function",
                        "function": {
                            "name": "call_env_sub_agent",
                            "arguments": json.dumps(
                                {
                                    "agent_query": (
                                        "Summarize warehouse facts for SKU-1 and highlight any "
                                        "inventory discrepancies."
                                    )
                                }
                            ),
                        },
                    }
                ],
                finish_reason="tool_calls",
            ),
            _make_llm_response(
                content=(
                    "FINAL ANSWER: The sub-agent found a 2-unit discrepancy for SKU-1 and no "
                    "other major warehouse issues."
                ),
            ),
        ]

        with patch("app.services.env_sub_agent.EnvSubAgent") as mock_env_sub_agent_cls:
            mock_env_sub_agent = mock_env_sub_agent_cls.return_value
            mock_env_sub_agent.run = AsyncMock(
                return_value={
                    "status": "completed",
                    "state_summary": (
                        "- System records show 10 units of SKU-1\n"
                        "- Physical count shows 8 units of SKU-1\n"
                        "- Discrepancy: physical stock is 2 units lower than system records"
                    ),
                    "total_tokens": 32,
                }
            )
            result = await agent.run("Check warehouse status for SKU-1")

        assert result["status"] == "completed"
        assert result["final_answer"] is not None
        assert "2-unit discrepancy" in result["final_answer"]
        mock_env_sub_agent_cls.assert_called_once_with(tool_registry=env_registry)
        assert mock_env_sub_agent.run.await_count == 1
        assert mock_env_sub_agent.run.await_args.kwargs == {
            "agent_query": (
                "Summarize warehouse facts for SKU-1 and highlight any inventory discrepancies."
            )
        }
        assert any(
            getattr(message, "type", "") == "tool"
            and "Discrepancy: physical stock is 2 units lower than system records"
            in str(message.content)
            for message in result["messages"]
        )

    @pytest.mark.asyncio()
    async def test_run_receives_structured_sub_agent_failure_observation(
        self, mock_llm_service: MagicMock
    ) -> None:
        mock_env_tool = MagicMock()
        mock_env_tool.metadata.name = "list_inventory_moves"

        env_registry = MagicMock()
        env_registry.list_tools.return_value = [mock_env_tool]

        tool_registry = ToolRegistryFactory.create_react_agent_registry(
            env_sub_registry=env_registry
        )
        agent = ReActAgent(tool_registry=tool_registry)

        mock_llm_service.chat_completion.side_effect = [
            _make_llm_response(
                content="I need environment facts before answering.",
                tool_calls=[
                    {
                        "id": "tc_1",
                        "type": "function",
                        "function": {
                            "name": "call_env_sub_agent",
                            "arguments": json.dumps({"agent_query": "Check SKU-1 history"}),
                        },
                    }
                ],
                finish_reason="tool_calls",
            ),
            _make_llm_response(
                content=(
                    "FINAL ANSWER: The environment lookup failed due to an upstream rate limit, "
                    "so inventory history could not be verified."
                ),
            ),
        ]

        with patch("app.services.env_sub_agent.EnvSubAgent") as mock_env_sub_agent_cls:
            mock_env_sub_agent = mock_env_sub_agent_cls.return_value
            mock_env_sub_agent.run = AsyncMock(
                return_value={
                    "status": "failed",
                    "error": "API rate limit exceeded.",
                    "state_summary": (
                        "- Environment API rate limit exceeded during inventory lookup."
                    ),
                }
            )
            result = await agent.run("Check warehouse status for SKU-1")

        assert result["status"] == "completed"
        assert result["final_answer"] is not None
        assert "rate limit" in result["final_answer"]
        assert any(
            getattr(message, "type", "") == "tool"
            and "Environment API rate limit exceeded during inventory lookup"
            in str(message.content)
            for message in result["messages"]
        )

    @pytest.mark.asyncio()
    async def test_run_max_iterations(self, agent: ReActAgent, mock_llm_service: MagicMock) -> None:
        """Agent stops before hitting the iteration limit (early check in _think_node)."""
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
        # 2 think calls: iteration 0 (calls LLM), iteration 1 (calls LLM)
        # Then iteration 2 would hit the check at start of _think_node (no LLM call)
        assert mock_llm_service.chat_completion.call_count == 2

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
