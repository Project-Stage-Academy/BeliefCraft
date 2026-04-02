import json
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.services.base_agent import BaseAgent
from app.tools.registry import ToolRegistry
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
    # Default successful execution
    registry.execute_tool = AsyncMock(
        return_value=MockToolResult(success=True, data={"result": "ok"})
    )

    # Mock tool metadata resolution for category lookup
    mock_metadata = MagicMock()
    mock_metadata.category = "utility"
    mock_tool = MagicMock()
    mock_tool.get_metadata.return_value = mock_metadata
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
    """Verifies that the ABC initialization sets up the required contracts."""
    assert agent.system_prompt == "Test Prompt"
    assert agent.tool_registry is mock_registry
    assert agent.graph is not None
    assert agent.llm is not None


# ---------------------------------------------------------------------------
# Pure / Static Utilities Tests (Data-Driven & Resilient)
# ---------------------------------------------------------------------------


class TestBaseAgentStaticUtilities:

    @pytest.mark.parametrize(
        "raw_args, expected",
        [
            # Case 1: Valid JSON string
            ('{"key": "value"}', {"key": "value"}),
            # Case 2: Already a dict
            ({"key": "value"}, {"key": "value"}),
            # Case 3: Empty JSON string
            ("{}", {}),
            # Case 4: Malformed JSON fallback
            ("not valid json", {"query": "not valid json"}),
            # Case 5: Empty string fallback
            ("", {"query": ""}),
        ],
        ids=["valid_json", "dict", "empty_json", "malformed_json", "empty_string"],
    )
    def test_parse_tool_arguments(self, raw_args: Any, expected: dict[str, Any]) -> None:
        """Verifies argument parsing gracefully handles varying tool payload qualities."""
        assert BaseAgent._parse_tool_arguments(raw_args) == expected

    @pytest.mark.parametrize(
        "category, raw_data, raw_meta, expected_data, expected_meta",
        [
            # Case 1: Standard non-environment tool (passes through as-is if dict)
            ("utility", {"some": "data"}, {"trace_id": 1}, {"some": "data"}, {"trace_id": 1}),
            # Case 2: Non-dict payload wrapped automatically
            ("rag", "plain text string", None, {"result": "plain text string"}, {}),
            # Case 3: Environment envelope unpacking (unwraps 'data' and 'meta')
            (
                "environment",
                {"data": {"items": [1]}, "meta": {"count": 1}},
                {},  # Initial meta is empty/ignored
                {"items": [1]},
                {"count": 1},
            ),
            # Case 4: Environment envelope but missing 'meta' inside -> fallback to safe defaults
            (
                "environment",
                {"data": {"items": [1]}},
                {"original": "meta"},
                {"data": {"items": [1]}},  # Does not unwrap because meta is missing from payload
                {"original": "meta"},
            ),
        ],
        ids=["standard", "non_dict_wrap", "env_unwrapping", "env_missing_meta"],
    )
    def test_normalize_tool_success_payload(
        self, category: str, raw_data: Any, raw_meta: Any, expected_data: dict, expected_meta: dict
    ) -> None:
        """Verifies that different shapes of tool responses are standardized correctly."""
        data, meta = BaseAgent._normalize_tool_success_payload(category, raw_data, raw_meta)
        assert data == expected_data
        assert meta == expected_meta


# ---------------------------------------------------------------------------
# Tool Execution Contract Tests
# ---------------------------------------------------------------------------


class TestBaseAgentToolExecution:

    def test_get_tool_category_success(
        self, agent: ConcreteTestAgent, mock_registry: MagicMock
    ) -> None:
        assert agent._get_tool_category("known_tool") == "utility"
        mock_registry.get_tool.assert_called_once_with("known_tool")

    def test_get_tool_category_fallback(
        self, agent: ConcreteTestAgent, mock_registry: MagicMock
    ) -> None:
        # If registry raises exception (tool not found), it should fail gracefully to None
        mock_registry.get_tool.side_effect = Exception("Not found")
        assert agent._get_tool_category("unknown_tool") is None

    @pytest.mark.asyncio
    async def test_execute_tool_success(
        self, agent: ConcreteTestAgent, mock_registry: MagicMock
    ) -> None:
        """Verifies successful tool execution returns standard success envelope."""
        mock_registry.execute_tool = AsyncMock(
            return_value=MockToolResult(success=True, data={"res": "ok"})
        )

        result = await agent._execute_tool("my_tool", {"arg": 1})

        assert result == {"status": "success", "data": {"res": "ok"}}

    @pytest.mark.asyncio
    async def test_execute_tool_managed_failure(
        self, agent: ConcreteTestAgent, mock_registry: MagicMock
    ) -> None:
        """Verifies tool failures (handled by registry) return standard error envelope."""
        mock_registry.execute_tool = AsyncMock(
            return_value=MockToolResult(success=False, error="Invalid args")
        )

        result = await agent._execute_tool("my_tool", {})

        assert result["status"] == "error"
        assert result["error"] == "Invalid args"
        assert "Tool execution failed" in result["message"]

    @pytest.mark.asyncio
    async def test_execute_tool_unhandled_exception(
        self, agent: ConcreteTestAgent, mock_registry: MagicMock
    ) -> None:
        """Verifies violent unhandled exceptions inside tools never crash the agent."""
        mock_registry.execute_tool = AsyncMock(side_effect=RuntimeError("DB Connection Lost"))

        result = await agent._execute_tool("my_tool", {})

        assert result["status"] == "error"
        assert result["error"] == "DB Connection Lost"
        assert "Unexpected tool error" in result["message"]

    @pytest.mark.asyncio
    async def test_execute_all_tools_orchestration(self, agent: ConcreteTestAgent) -> None:
        """
        Tests the end-to-end processing of a list of LLM-generated tool calls.
        Verifies correct formatting of the resulting messages and state objects.
        """
        pending_calls = [
            {
                "id": "call_success",
                "function": {"name": "good_tool", "arguments": '{"query": "data"}'},
            },
            {"id": "call_fail", "function": {"name": "bad_tool", "arguments": "{}"}},
        ]

        # Intercept the individual executor to return deterministic responses
        async def mock_execute_tool(name: str, args: dict) -> dict:
            if name == "good_tool":
                return {"status": "success", "data": {"found": True}}
            return {"status": "error", "error": "Not found"}

        agent._execute_tool = mock_execute_tool  # type: ignore
        agent._get_tool_category = MagicMock(return_value="utility")

        new_messages, tool_results = await agent._execute_all_tools(pending_calls, "req_123")

        # Verify new messages format for LLM context
        assert len(new_messages) == 2
        assert new_messages[0]["tool_call_id"] == "call_success"
        assert new_messages[0]["name"] == "good_tool"
        assert json.loads(new_messages[0]["content"]) == {"found": True}

        assert new_messages[1]["tool_call_id"] == "call_fail"
        assert json.loads(new_messages[1]["content"]) == {"error": "Not found"}

        # Verify structured tool_results format for State
        assert len(tool_results) == 2
        assert tool_results[0]["tool_name"] == "good_tool"
        assert tool_results[0]["result"] == {"found": True}

        assert tool_results[1]["tool_name"] == "bad_tool"
        assert tool_results[1]["error"] == "Not found"


# ---------------------------------------------------------------------------
# LLM Communication Tests
# ---------------------------------------------------------------------------


class TestBaseAgentLLMCommunication:

    @pytest.mark.asyncio
    async def test_call_llm_passes_tools_and_choice(
        self, agent: ConcreteTestAgent, mock_registry: MagicMock
    ) -> None:
        """Ensures the base agent dynamically binds tools from the registry to the LLM call."""
        mock_schema = [{"type": "function", "function": {"name": "test"}}]
        mock_registry.get_openai_functions.return_value = mock_schema

        agent.llm.chat_completion = AsyncMock(return_value={"message": "ok"})

        messages = [{"role": "user", "content": "hi"}]
        result = await agent._call_llm(messages)

        assert result == {"message": "ok"}
        agent.llm.chat_completion.assert_called_once_with(
            messages=messages, tools=mock_schema, tool_choice="auto"
        )
