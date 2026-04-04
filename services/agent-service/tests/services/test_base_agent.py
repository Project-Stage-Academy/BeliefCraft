from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.services.base_agent import BaseAgent
from app.tools.registry import ToolRegistry
from langchain_core.tools import StructuredTool
from langgraph.graph.state import CompiledStateGraph

# ---------------------------------------------------------------------------
# Stubs & Helpers
# ---------------------------------------------------------------------------


class ConcreteTestAgent(BaseAgent):
    """A concrete implementation of the BaseAgent purely for testing."""

    def _build_graph(self) -> CompiledStateGraph[Any, Any, Any, Any]:
        return MagicMock(spec=CompiledStateGraph)

    async def run(self, *args: Any, **kwargs: Any) -> Any:
        return {"status": "success"}


@dataclass
class MockToolResult:
    """Mocks the return type of ToolRegistry.execute_tool()"""

    success: bool
    data: Any = None
    error: str | None = None


@pytest.fixture
def mock_registry() -> MagicMock:
    registry = MagicMock(spec=ToolRegistry)

    # Mock tool metadata resolution for category lookup
    mock_metadata = MagicMock()
    mock_metadata.name = "test_tool"
    mock_metadata.description = "A test tool"
    mock_metadata.parameters = {"type": "object", "properties": {}}  # Must be a real dict
    mock_metadata.category = "utility"

    mock_tool = MagicMock()
    mock_tool.metadata = mock_metadata  # <-- ADDED: Mock the property, not just the method
    mock_tool.get_metadata.return_value = mock_metadata
    mock_tool.run = AsyncMock(return_value=MockToolResult(success=True, data={"result": "ok"}))

    registry.list_tools.return_value = [mock_tool]
    registry.get_tool.return_value = mock_tool

    return registry


@pytest.fixture
def agent(mock_registry: MagicMock) -> ConcreteTestAgent:
    # Patch LLMService so it doesn't try to instantiate real Bedrock clients
    with patch("app.services.base_agent.LLMService"):
        return ConcreteTestAgent(
            model_id="test-model-id",
            system_prompt="Test Prompt",
            tool_registry=mock_registry,
        )


# ---------------------------------------------------------------------------
# Initialization Tests
# ---------------------------------------------------------------------------


def test_base_agent_initialization(agent: ConcreteTestAgent, mock_registry: MagicMock) -> None:
    """Verifies that the ABC initialization sets up the required contracts and LangChain tools."""
    assert agent.system_prompt == "Test Prompt"
    assert agent.tool_registry is mock_registry
    assert agent.graph is not None
    assert agent.llm is not None
    assert len(agent.lc_tools) == 1
    assert isinstance(agent.lc_tools[0], StructuredTool)
    assert agent.lc_tools[0].name == "test_tool"


# ---------------------------------------------------------------------------
# LLM Communication Tests
# ---------------------------------------------------------------------------


class TestBaseAgentLLMCommunication:

    @pytest.mark.asyncio
    async def test_call_llm_passes_tools_implicitly(self, agent: ConcreteTestAgent) -> None:
        """Ensures the base agent calls the LLM (tools are bound during initialization)."""
        agent.llm.chat_completion = AsyncMock(return_value={"message": "ok"})

        messages = [{"role": "user", "content": "hi"}]
        result = await agent._call_llm(messages)

        assert result == {"message": "ok"}
        agent.llm.chat_completion.assert_called_once_with(messages=messages)
