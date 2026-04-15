# services/agent-service/tests/integration/test_env_sub_agent_integration.py
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Fixed imports: these models live in _plans, not _state
from app.services.env_sub_agent import EnvSubAgent
from app.tools.registry import ToolRegistry


def _make_lc_tool(name: str, result: MagicMock):
    """Helper to create a mock LangChain tool."""
    tool = MagicMock()
    tool.name = name
    tool.description = f"Description for {name}"
    tool.invoke = MagicMock(return_value=result)
    tool.ainvoke = AsyncMock(return_value=result)
    return tool


@pytest.fixture
def mock_registry() -> MagicMock:
    registry = MagicMock(spec=ToolRegistry)
    # Ensure list_tools returns enough for the graph initialization if needed
    registry.list_tools.return_value = []
    return registry


@pytest.fixture
def agent(mock_registry: MagicMock) -> EnvSubAgent:
    """
    Fixture to initialize EnvSubAgent with mocked LLM components.
    Targeting the base_agent namespace where LLMService is looked up.
    """
    with patch("app.services.base_agent.LLMService") as mock_llm_cls:
        mock_llm_instance = mock_llm_cls.return_value
        # Pre-set as AsyncMocks to avoid TypeError during await
        mock_llm_instance.chat_completion = AsyncMock()
        mock_llm_instance.structured_completion = AsyncMock()

        return EnvSubAgent(tool_registry=mock_registry)


@pytest.mark.asyncio
async def test_env_sub_agent_run_distills_inventory_discrepancy(agent: EnvSubAgent) -> None:
    # Setup LLM sequences using agent.llm (not solver_llm)
    agent.llm.chat_completion.side_effect = [
        # Call 1: Reason and decide to call tools
        {
            "message": {"role": "assistant", "content": "Checking inventory..."},
            "tool_calls": [
                {
                    "id": "call_1",
                    "function": {
                        "name": "list_inventory_moves",
                        "arguments": '{"product_id": "SKU-1"}',
                    },
                }
            ],
            "model_id": "test-model",
            "tokens": {"prompt": 10, "completion": 5, "total": 15},
        },
        # Call 2: Final answer
        {
            "message": {
                "role": "assistant",
                "content": "- Discrepancy: physical stock is 2 units lower than system records",
            },
            "tool_calls": [],
            "model_id": "test-model",
            "tokens": {"prompt": 10, "completion": 5, "total": 15},
        },
    ]

    inventory_result = MagicMock()
    inventory_result.success = True
    inventory_result.data = {"data": [{"move_id": "123", "quantity": 10}]}

    # Inject tools
    agent.lc_tools = [_make_lc_tool("list_inventory_moves", inventory_result)]

    final_state = await agent.run("Check whether SKU-1 has an inventory discrepancy")

    assert final_state["status"] == "completed"
    assert "Discrepancy" in final_state["state_summary"]
    assert final_state["completed_at"] is not None


@pytest.mark.asyncio
async def test_env_sub_agent_run_handles_solver_failure(agent: EnvSubAgent) -> None:
    # Simulate LLM failure during ReAct loop
    agent.llm.chat_completion.side_effect = RuntimeError("solver LLM unavailable")

    final_state = await agent.run("Check inventory discrepancy for SKU-1")

    assert final_state["status"] == "failed"
    assert "solver LLM unavailable" in final_state["error"]


@pytest.mark.asyncio
async def test_env_sub_agent_run_handles_empty_plan(agent: EnvSubAgent) -> None:
    """
    Verifies behavior when the LLM returns no tool calls and no useful answer.
    """
    agent.llm.chat_completion.return_value = {
        "message": {"role": "assistant", "content": "I don't know how to help with that."},
        "tool_calls": [],
        "model_id": "test-model",
        "tokens": {"total": 10},
    }

    final_state = await agent.run("Check inventory discrepancy for SKU-1")

    # In a ReAct loop, if it returns an answer immediately with no tools,
    # it is usually considered a completion.
    assert final_state["status"] == "completed"
    assert "don't know" in final_state["state_summary"]


@pytest.mark.asyncio
async def test_env_sub_agent_run_catches_max_iterations(agent: EnvSubAgent) -> None:
    # Force limit
    agent.max_iterations = 1

    agent.llm.chat_completion.return_value = {
        "message": {"role": "assistant", "content": "Thinking..."},
        "tool_calls": [{"id": "c1", "function": {"name": "t", "arguments": "{}"}}],
        "model_id": "test-model",
        "tokens": {"total": 10},
    }
    agent.lc_tools = [_make_lc_tool("t", MagicMock())]

    final_state = await agent.run("Endless loop")

    assert final_state["status"] == "failed"
    assert "Reached max iteration limit" in final_state["error"]
