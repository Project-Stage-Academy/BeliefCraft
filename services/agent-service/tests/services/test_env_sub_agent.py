# file: services/agent-service/tests/services/test_env_sub_agent.py
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.config_load import settings
from app.core.exceptions import AgentExecutionError
from app.models.env_sub_agent_state import ReActState, create_initial_state
from app.services.env_sub_agent import EnvSubAgent
from app.tools.base import ToolMetadata
from app.tools.registry import ToolRegistry
from langchain_core.messages import AIMessage
from langchain_core.tools import tool
from langgraph.graph import StateGraph
from langgraph.prebuilt import ToolNode

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_registry() -> MagicMock:
    registry = MagicMock(spec=ToolRegistry)

    # We use actual functions so ToolNode can inspect type hints,
    # but we still capture calls using a mock internally.
    async def mock_run_1(**kwargs):
        return {"data": "tool_a_result"}

    async def mock_run_2(**kwargs):
        return {"data": "tool_b_result"}

    mock_tool_1 = MagicMock()
    mock_tool_1.metadata = ToolMetadata(
        name="get_inventory",
        description="Gets stock",
        category="environment",
        parameters={"type": "object"},
    )
    # Ensure the 'run' attribute is a real function
    mock_tool_1.run = mock_run_1

    mock_tool_2 = MagicMock()
    mock_tool_2.metadata = ToolMetadata(
        name="get_devices",
        description="Gets sensors",
        category="environment",
        parameters={"type": "object"},
    )
    mock_tool_2.run = mock_run_2

    registry.list_tools.return_value = [mock_tool_1, mock_tool_2]
    return registry


@pytest.fixture
def agent(mock_registry: MagicMock) -> EnvSubAgent:
    with patch("app.services.base_agent.LLMService"):
        return EnvSubAgent(tool_registry=mock_registry, max_iterations=3)


@pytest.fixture
def initial_state() -> ReActState:
    return create_initial_state(agent_query="Check inventory and sensors")


# ---------------------------------------------------------------------------
# Initialization Tests
# ---------------------------------------------------------------------------


def test_initialization_requires_registry() -> None:
    with pytest.raises(ValueError, match="must be explicitly injected"):
        EnvSubAgent(tool_registry=None)


def test_initialization_builds_graph(agent: EnvSubAgent) -> None:
    assert agent.graph is not None
    assert agent.system_prompt is not None


def test_initialization_uses_react_model(mock_registry: MagicMock) -> None:
    with patch("app.services.base_agent.LLMService") as base_llm_cls:
        agent = EnvSubAgent(tool_registry=mock_registry)

    base_llm_cls.assert_called_once_with(model_id=settings.react_agent.model_id)
    assert agent.llm is base_llm_cls.return_value


# ---------------------------------------------------------------------------
# Reason Node Tests
# ---------------------------------------------------------------------------


class TestReasonNode:

    @pytest.mark.asyncio
    async def test_reason_node_success_with_tools(
        self, agent: EnvSubAgent, initial_state: ReActState
    ) -> None:
        """Verifies the reason node maps OpenAI tool calls to LangChain tool calls."""
        agent.llm.chat_completion = AsyncMock(
            return_value={
                "message": {"role": "assistant", "content": "Thinking..."},
                "tool_calls": [
                    {
                        "id": "call_abc123",
                        "type": "function",
                        "function": {
                            "name": "get_inventory",
                            "arguments": '{"wh": "A"}',
                        },
                    }
                ],
                "model_id": "test-model",
                "tokens": {"total": 15},
            }
        )

        result = await agent._reason_node(initial_state)

        assert result["step_count"] == 1
        assert result["token_usage"]["test-model"]["total"] == 15

        msg = result["messages"][0]
        assert isinstance(msg, AIMessage)
        assert msg.content == "Thinking..."

        # Verify tool calls are transcoded properly
        assert len(msg.tool_calls) == 1
        tc = msg.tool_calls[0]
        assert tc["name"] == "get_inventory"
        assert tc["args"] == {"wh": "A"}
        assert tc["id"] == "call_abc123"

    @pytest.mark.asyncio
    async def test_reason_node_handles_llm_exception(
        self, agent: EnvSubAgent, initial_state: ReActState
    ) -> None:
        """Verifies LLM failures are caught gracefully and return a failed status."""
        agent.llm.chat_completion = AsyncMock(side_effect=Exception("API Timeout"))

        result = await agent._reason_node(initial_state)

        assert result["status"] == "failed"
        assert "API Timeout" in result["error"]
        assert result["completed_at"] is not None


# ---------------------------------------------------------------------------
# Act Node Tests
# ---------------------------------------------------------------------------
# tests/services/test_env_sub_agent.py


class TestActNode:

    @pytest.mark.asyncio
    async def test_act_node_concurrent_success(self, initial_state: ReActState) -> None:
        """Verifies multiple tools are executed and formatted correctly."""
        initial_state["messages"] = [
            AIMessage(
                content="",
                tool_calls=[
                    {"id": "call_1", "name": "tool_a", "args": {"id": 1}},
                    {"id": "call_2", "name": "tool_b", "args": {"id": 2}},
                ],
            )
        ]

        @tool
        async def tool_a(id: int) -> dict:
            """A"""
            return {"data": "tool_a_result"}

        @tool
        async def tool_b(id: int) -> dict:
            """B"""
            return {"data": "tool_b_result"}

        # Fix: Execute using a compiled graph to ensure LangGraph injects required context
        workflow = StateGraph(ReActState)
        workflow.add_node("act", ToolNode([tool_a, tool_b]))
        workflow.set_entry_point("act")
        graph = workflow.compile()

        result = await graph.ainvoke(initial_state)

        messages = result["messages"]
        # The result returns the full state (1 input AIMessage + 2 new ToolMessages)
        assert len(messages) == 3

        assert messages[1].type == "tool"
        assert messages[1].tool_call_id == "call_1"
        assert messages[1].name == "tool_a"
        assert "tool_a_result" in str(messages[1].content)

        assert messages[2].type == "tool"
        assert messages[2].tool_call_id == "call_2"
        assert messages[2].name == "tool_b"
        assert "tool_b_result" in str(messages[2].content)

    @pytest.mark.asyncio
    async def test_act_node_handles_tool_crash(self, initial_state: ReActState) -> None:
        """Verifies that unhandled tool exceptions are raised by ToolNode."""
        initial_state["messages"] = [
            AIMessage(
                content="",
                tool_calls=[{"id": "call_bad", "name": "tool_crash", "args": {}}],
            )
        ]

        @tool
        async def tool_crash() -> str:
            """crash"""
            raise RuntimeError("Catastrophic Failure")

        workflow = StateGraph(ReActState)
        workflow.add_node("act", ToolNode([tool_crash]))
        workflow.set_entry_point("act")
        graph = workflow.compile()

        with pytest.raises(RuntimeError, match="Catastrophic Failure"):
            await graph.ainvoke(initial_state)

    @pytest.mark.asyncio
    async def test_act_node_handles_missing_tool(self, initial_state: ReActState) -> None:
        """Verifies that missing tools are handled smoothly by ToolNode."""
        initial_state["messages"] = [
            AIMessage(
                content="",
                tool_calls=[{"id": "call_missing", "name": "fake_tool", "args": {}}],
            )
        ]

        @tool
        async def real_tool() -> str:
            """real"""
            return ""

        workflow = StateGraph(ReActState)
        workflow.add_node("act", ToolNode([real_tool]))
        workflow.set_entry_point("act")
        graph = workflow.compile()

        result = await graph.ainvoke(initial_state)

        msg = result["messages"][-1]
        # Change 'not found' to 'not a valid tool' or check for 'error'
        assert "not a valid tool" in str(msg.content).lower()
        assert msg.name == "fake_tool"


# ---------------------------------------------------------------------------
# Graph Routing Tests
# ---------------------------------------------------------------------------


class TestGraphRouting:

    def test_should_continue_ends_on_failure(
        self, agent: EnvSubAgent, initial_state: ReActState
    ) -> None:
        initial_state["status"] = "failed"
        assert agent._should_continue(initial_state) == "end"

    def test_should_continue_ends_on_iteration_limit(
        self, agent: EnvSubAgent, initial_state: ReActState
    ) -> None:
        initial_state["status"] = "running"
        initial_state["step_count"] = 3
        assert agent._should_continue(initial_state) == "end"

    def test_should_continue_routes_to_act(
        self, agent: EnvSubAgent, initial_state: ReActState
    ) -> None:
        initial_state["status"] = "running"
        initial_state["step_count"] = 1
        initial_state["messages"] = [
            AIMessage(content="", tool_calls=[{"id": "1", "name": "t", "args": {}}])
        ]
        assert agent._should_continue(initial_state) == "continue"

    def test_should_continue_ends_when_done(
        self, agent: EnvSubAgent, initial_state: ReActState
    ) -> None:
        initial_state["status"] = "running"
        initial_state["step_count"] = 1
        initial_state["messages"] = [AIMessage(content="Final Answer")]
        assert agent._should_continue(initial_state) == "end"


# ---------------------------------------------------------------------------
# Run Loop Tests
# ---------------------------------------------------------------------------


class TestRunMethod:

    @pytest.mark.asyncio
    async def test_run_success(self, agent: EnvSubAgent) -> None:
        """Verifies run() successfully invokes the LangGraph state machine and sets summary."""
        mock_final_state = create_initial_state(agent_query="test")
        mock_final_state["messages"] = [AIMessage(content="The stock is 50.")]
        mock_final_state["status"] = "running"

        agent.graph.ainvoke = AsyncMock(return_value=mock_final_state)

        result = await agent.run(agent_query="Check stock")

        assert result["status"] == "completed"
        assert result["state_summary"] == "The stock is 50."
        assert result["completed_at"] is not None
        agent.graph.ainvoke.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_halts_on_max_iterations(self, agent: EnvSubAgent) -> None:
        """Verifies the agent sets a failed status if the
        loop ended purely due to iteration limits."""
        mock_final_state = create_initial_state(agent_query="test")
        mock_final_state["step_count"] = agent.max_iterations
        mock_final_state["status"] = "running"

        agent.graph.ainvoke = AsyncMock(return_value=mock_final_state)

        result = await agent.run(agent_query="Infinite loop task")

        assert result["status"] == "failed"
        assert "Reached max iteration limit" in result["error"]
        assert result["completed_at"] is not None

    @pytest.mark.asyncio
    async def test_run_catches_execution_error(self, agent: EnvSubAgent) -> None:
        """Verifies critical graph crashes are wrapped in AgentExecutionError."""
        agent.graph.ainvoke = AsyncMock(side_effect=ValueError("Graph compilation error"))

        with pytest.raises(
            AgentExecutionError, match="EnvSubAgent execution failed.*Graph compilation error"
        ):
            await agent.run(agent_query="Break the graph")
