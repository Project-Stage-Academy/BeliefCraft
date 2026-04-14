from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.config_load import settings
from app.core.exceptions import AgentExecutionError
from app.models.env_sub_agent_plans import PlannedToolCall, WarehousePlan
from app.models.env_sub_agent_state import ReWOOState, create_initial_state
from app.services.env_sub_agent import EnvSubAgent
from app.tools.base import ToolMetadata
from app.tools.registry import ToolRegistry

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_registry() -> MagicMock:
    registry = MagicMock(spec=ToolRegistry)

    # Create some mock tools with metadata for the planner prompt
    mock_tool_1 = MagicMock()
    mock_tool_1.metadata = ToolMetadata(
        name="get_inventory", description="Gets stock", category="environment", parameters={}
    )
    mock_tool_1.run = AsyncMock()

    mock_tool_2 = MagicMock()
    mock_tool_2.metadata = ToolMetadata(
        name="get_devices", description="Gets sensors", category="environment", parameters={}
    )
    mock_tool_2.run = AsyncMock()

    registry.list_tools.return_value = [mock_tool_1, mock_tool_2]
    return registry


@pytest.fixture
def agent(mock_registry: MagicMock) -> EnvSubAgent:
    with (
        patch("app.services.base_agent.LLMService"),
        patch("app.services.env_sub_agent.LLMService"),
    ):
        return EnvSubAgent(tool_registry=mock_registry)


@pytest.fixture
def initial_state() -> ReWOOState:
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


def test_initialization_uses_separate_planner_and_solver_models(
    mock_registry: MagicMock,
) -> None:
    with (
        patch("app.services.base_agent.LLMService") as planner_llm_cls,
        patch("app.services.env_sub_agent.LLMService") as solver_llm_cls,
    ):
        agent = EnvSubAgent(tool_registry=mock_registry)

    planner_llm_cls.assert_called_once_with(model_id=settings.env_sub_agent.planner_model_id)
    solver_llm_cls.assert_called_once_with(model_id=settings.env_sub_agent.solver_model_id)
    assert agent.solver_llm is solver_llm_cls.return_value


# ---------------------------------------------------------------------------
# Plan Node Tests
# ---------------------------------------------------------------------------


class TestPlanNode:

    @pytest.mark.asyncio
    async def test_plan_node_success_with_pydantic_model(
        self, agent: EnvSubAgent, initial_state: ReWOOState
    ) -> None:
        """Verifies the planner node correctly handles a native
        WarehousePlan returned by the LLM."""
        mock_plan = WarehousePlan(
            tool_calls=[
                PlannedToolCall(
                    rationale="Need stock", tool_name="get_inventory", arguments={"wh": "A"}
                ),
            ]
        )

        agent.llm.structured_completion = AsyncMock(
            return_value={
                "result": mock_plan,
                "tokens": {"prompt": 9, "completion": 4, "total": 13},
            }
        )

        result = await agent._plan_node(initial_state)

        assert result["status"] == "executing"
        assert result["plan"] is mock_plan
        assert result["total_tokens"] == 13
        agent.llm.structured_completion.assert_called_once()

    @pytest.mark.asyncio
    async def test_plan_node_success_with_raw_dict(
        self, agent: EnvSubAgent, initial_state: ReWOOState
    ) -> None:
        """Verifies the planner node correctly casts a raw dict response into a WarehousePlan."""
        raw_dict_plan = {
            "tool_calls": [
                {"rationale": "Need sensors", "tool_name": "get_devices", "arguments": {}}
            ]
        }

        agent.llm.structured_completion = AsyncMock(
            return_value={
                "result": raw_dict_plan,
                "tokens": {"prompt": 7, "completion": 5, "total": 12},
            }
        )

        result = await agent._plan_node(initial_state)

        assert result["status"] == "executing"
        assert isinstance(result["plan"], WarehousePlan)
        assert result["plan"].tool_calls[0].tool_name == "get_devices"
        assert result["total_tokens"] == 12

    @pytest.mark.asyncio
    async def test_plan_node_handles_llm_exception(
        self, agent: EnvSubAgent, initial_state: ReWOOState
    ) -> None:
        """Verifies LLM failures are caught gracefully and return a failed status."""
        agent.llm.structured_completion = AsyncMock(side_effect=Exception("API Timeout"))

        result = await agent._plan_node(initial_state)

        assert result["status"] == "failed"
        assert "API Timeout" in result["error"]
        assert result["completed_at"] is not None

    @pytest.mark.asyncio
    async def test_plan_node_accumulates_existing_total_tokens(
        self, agent: EnvSubAgent, initial_state: ReWOOState
    ) -> None:
        initial_state["total_tokens"] = 10
        mock_plan = WarehousePlan(
            tool_calls=[
                PlannedToolCall(
                    rationale="Need stock", tool_name="get_inventory", arguments={"wh": "A"}
                )
            ]
        )
        agent.llm.structured_completion = AsyncMock(
            return_value={
                "result": mock_plan,
                "tokens": {"prompt": 6, "completion": 3, "total": 9},
            }
        )

        result = await agent._plan_node(initial_state)

        assert result["status"] == "executing"
        assert result["total_tokens"] == 19


# ---------------------------------------------------------------------------
# Execute Node Tests
# ---------------------------------------------------------------------------


class TestExecuteNode:

    @pytest.mark.asyncio
    async def test_execute_node_fails_on_empty_plan(
        self, agent: EnvSubAgent, initial_state: ReWOOState
    ) -> None:
        initial_state["plan"] = None
        result = await agent._execute_node(initial_state)

        assert result["status"] == "failed"
        assert "No tools planned" in result["error"]
        assert result["completed_at"] is not None

    @pytest.mark.asyncio
    async def test_execute_node_fails_on_empty_tool_calls(
        self, agent: EnvSubAgent, initial_state: ReWOOState
    ) -> None:
        initial_state["plan"] = WarehousePlan(tool_calls=[])
        result = await agent._execute_node(initial_state)

        assert result["status"] == "failed"
        assert "No tools planned" in result["error"]
        assert result["completed_at"] is not None

    @pytest.mark.asyncio
    async def test_execute_node_concurrent_success(
        self, agent: EnvSubAgent, initial_state: ReWOOState
    ) -> None:
        """Verifies multiple tools are executed, indexed correctly,
        and formatted into observations."""
        initial_state["plan"] = WarehousePlan(
            tool_calls=[
                PlannedToolCall(rationale="1", tool_name="tool_a", arguments={"id": 1}),
                PlannedToolCall(rationale="2", tool_name="tool_b", arguments={"id": 2}),
                PlannedToolCall(rationale="3", tool_name="tool_a", arguments={"id": 3}),
            ]
        )

        # Mock the LangChain structured tools
        mock_tool_a = MagicMock()
        mock_tool_a.name = "tool_a"
        mock_tool_a.ainvoke = AsyncMock(return_value=MagicMock(success=True, data="tool_a_result"))

        mock_tool_b = MagicMock()
        mock_tool_b.name = "tool_b"
        mock_tool_b.ainvoke = AsyncMock(return_value=MagicMock(success=True, data="tool_b_result"))

        agent.lc_tools = [mock_tool_a, mock_tool_b]

        result = await agent._execute_node(initial_state)

        assert result["status"] == "solving"
        obs = result["observations"]

        assert len(obs) == 3
        # Keys should have the index appended to ensure uniqueness
        assert "tool_a_0" in obs
        assert "tool_b_1" in obs
        assert "tool_a_2" in obs

        assert obs["tool_a_0"]["response"]["data"] == "tool_a_result"
        assert obs["tool_b_1"]["response"]["data"] == "tool_b_result"
        assert obs["tool_a_2"]["response"]["data"] == "tool_a_result"

        # Verify schema
        assert obs["tool_a_0"]["tool"] == "tool_a"
        assert obs["tool_a_0"]["arguments"] == {"id": 1}

    @pytest.mark.asyncio
    async def test_execute_node_handles_gather_exceptions(
        self, agent: EnvSubAgent, initial_state: ReWOOState
    ) -> None:
        """Verifies that if tool.ainvoke violently crashes,
        gather() exceptions are formatted safely."""
        initial_state["plan"] = WarehousePlan(
            tool_calls=[
                PlannedToolCall(rationale="1", tool_name="tool_crash", arguments={}),
            ]
        )

        mock_tool = MagicMock()
        mock_tool.name = "tool_crash"
        mock_tool.ainvoke = AsyncMock(side_effect=RuntimeError("Catastrophic Failure"))
        agent.lc_tools = [mock_tool]

        result = await agent._execute_node(initial_state)

        assert result["status"] == "solving"  # Should continue to solve even if tools failed
        obs = result["observations"]["tool_crash_0"]["response"]

        assert obs["status"] == "error"
        assert "Catastrophic Failure" in obs["error"]
        assert "Unhandled exception: RuntimeError" in obs["message"]


# ---------------------------------------------------------------------------
# Solve Node Tests
# ---------------------------------------------------------------------------


class TestSolveNode:
    @pytest.mark.asyncio
    async def test_solve_node_returns_bulleted_fallback_without_observations(
        self, agent: EnvSubAgent, initial_state: ReWOOState
    ) -> None:
        result = await agent._solve_node(initial_state)

        assert result["status"] == "completed"
        assert result["state_summary"].startswith("- ")
        assert "Insufficient data" in result["state_summary"]

    @pytest.mark.asyncio
    async def test_solve_node_uses_chat_completion_and_tracks_tokens(
        self, agent: EnvSubAgent, initial_state: ReWOOState
    ) -> None:
        initial_state["observations"] = {
            "inventory_moves_0": {
                "tool": "list_inventory_moves",
                "arguments": {"sku": "SKU-1"},
                "response": {"status": "success", "data": {"moves": [{"quantity": 10}]}},
            }
        }
        initial_state["total_tokens"] = 12

        agent.solver_llm.chat_completion = AsyncMock(
            return_value={
                "message": {"role": "assistant", "content": "- 10 units moved for SKU-1"},
                "tool_calls": [],
                "finish_reason": "stop",
                "tokens": {"prompt": 8, "completion": 6, "total": 14},
            }
        )

        result = await agent._solve_node(initial_state)

        assert result["status"] == "completed"
        assert result["state_summary"] == "- 10 units moved for SKU-1"
        assert result["total_tokens"] == 26
        solver_messages = agent.solver_llm.chat_completion.call_args.kwargs["messages"]
        solver_prompt = solver_messages[1]["content"]
        assert "inventory_moves_0" in solver_prompt

    @pytest.mark.asyncio
    async def test_solve_node_passes_raw_observations_to_solver_prompt(
        self, agent: EnvSubAgent, initial_state: ReWOOState
    ) -> None:
        initial_state["observations"] = {
            "inventory_moves_0": {
                "tool": "list_inventory_moves",
                "arguments": {"product_id": "04fc58b7-f457-4661-a916-3c3d0ac93cdf"},
                "response": {
                    "status": "success",
                    "data": {
                        "moves": [
                            {
                                "id": "123e4567-e89b-12d3-a456-426614174000",
                                "to_location_id": "6901725d-1dbd-4146-a02e-2d7bc1111111",
                            }
                        ]
                    },
                },
            }
        }

        agent.solver_llm.chat_completion = AsyncMock(
            return_value={
                "message": {"role": "assistant", "content": "- Sanitized summary"},
                "tool_calls": [],
                "finish_reason": "stop",
                "tokens": {"prompt": 8, "completion": 6, "total": 14},
            }
        )

        await agent._solve_node(initial_state)

        solver_messages = agent.solver_llm.chat_completion.call_args.kwargs["messages"]
        solver_prompt = solver_messages[1]["content"]

        assert "04fc58b7-f457-4661-a916-3c3d0ac93cdf" in solver_prompt
        assert "123e4567-e89b-12d3-a456-426614174000" in solver_prompt
        assert "6901725d-1dbd-4146-a02e-2d7bc1111111" in solver_prompt
        assert '"product_id": "04fc58b7-f457-4661-a916-3c3d0ac93cdf"' in solver_prompt
        assert '"id": "123e4567-e89b-12d3-a456-426614174000"' in solver_prompt
        assert '"to_location_id": "6901725d-1dbd-4146-a02e-2d7bc1111111"' in solver_prompt

    @pytest.mark.asyncio
    async def test_solve_node_surfaces_error_field_on_failure(
        self, agent: EnvSubAgent, initial_state: ReWOOState
    ) -> None:
        initial_state["observations"] = {
            "tool_0": {"tool": "get_inventory", "arguments": {}, "response": {"status": "success"}}
        }
        agent.solver_llm.chat_completion = AsyncMock(side_effect=RuntimeError("solver boom"))

        result = await agent._solve_node(initial_state)

        assert result["status"] == "failed"
        assert result["error"] == "solver boom"
        assert result["state_summary"].startswith("- Solver processing failed:")


# ---------------------------------------------------------------------------
# Run Loop Tests
# ---------------------------------------------------------------------------


class TestRunMethod:

    @pytest.mark.asyncio
    async def test_run_success(self, agent: EnvSubAgent) -> None:
        """Verifies run() successfully invokes the LangGraph state machine."""
        mock_final_state = create_initial_state(agent_query="test")
        mock_final_state["status"] = "completed"

        agent.graph.ainvoke = AsyncMock(return_value=mock_final_state)

        result = await agent.run(agent_query="Do a test run")

        assert result["status"] == "completed"
        agent.graph.ainvoke.assert_called_once()

        # Check that the initial state passed to the graph has the correct query
        called_state = agent.graph.ainvoke.call_args[0][0]
        assert called_state["agent_query"] == "Do a test run"

    @pytest.mark.asyncio
    async def test_run_catches_execution_error(self, agent: EnvSubAgent) -> None:
        """Verifies critical graph crashes are wrapped in AgentExecutionError."""
        agent.graph.ainvoke = AsyncMock(side_effect=ValueError("Graph compilation error"))

        with pytest.raises(
            AgentExecutionError, match="EnvSubAgent execution failed.*Graph compilation error"
        ):
            await agent.run(agent_query="Break the graph")
