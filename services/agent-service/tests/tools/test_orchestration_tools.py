from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.tools.base import ToolMetadata
from app.tools.orchestration_tools import CallEnvSubAgentTool


@pytest.fixture
def mock_registry():
    registry_mock = MagicMock()

    tool_1 = MagicMock()
    tool_1.metadata.name = "get_stock_levels"

    tool_2 = MagicMock()
    tool_2.metadata.name = "get_pallet_location"

    registry_mock.list_tools.return_value = [tool_1, tool_2]
    return registry_mock


@pytest.fixture
def tool(mock_registry):
    return CallEnvSubAgentTool(env_registry=mock_registry)


def test_get_metadata(tool):
    metadata = tool.get_metadata()

    assert isinstance(metadata, ToolMetadata)
    assert metadata.name == "call_env_sub_agent"
    assert "[get_stock_levels, get_pallet_location]" in metadata.description
    assert "agent_query" in metadata.parameters["properties"]
    assert metadata.parameters["required"] == ["agent_query"]


@pytest.mark.asyncio
@patch.object(CallEnvSubAgentTool, "_validate_required_params")
@patch("app.services.env_sub_agent.EnvSubAgent")
async def test_execute_success_with_summary(mock_sub_agent_class, mock_validate, tool):
    mock_instance = mock_sub_agent_class.return_value
    mock_instance.run = AsyncMock(
        return_value={"status": "success", "state_summary": "All palettes are in sector 4G."}
    )

    result = await tool.execute(agent_query="Where are the palettes?")

    mock_validate.assert_called_once_with(
        ["agent_query"], {"agent_query": "Where are the palettes?"}
    )
    mock_sub_agent_class.assert_called_once_with(tool_registry=tool.env_registry)
    mock_instance.run.assert_awaited_once_with(agent_query="Where are the palettes?")

    assert result == {
        "summary": "All palettes are in sector 4G.",
        "token_usage": {},
    }


@pytest.mark.asyncio
@patch.object(CallEnvSubAgentTool, "_validate_required_params")
@patch("app.services.env_sub_agent.EnvSubAgent")
async def test_execute_success_no_summary(mock_sub_agent_class, mock_validate, tool):
    mock_instance = mock_sub_agent_class.return_value
    mock_instance.run = AsyncMock(return_value={"status": "success", "state_summary": ""})

    result = await tool.execute(agent_query="Check anomalies.")

    assert result == {
        "summary": "Sub-agent completed but generated no summary.",
        "token_usage": {},
    }


@pytest.mark.asyncio
@patch.object(CallEnvSubAgentTool, "_validate_required_params")
@patch("app.services.env_sub_agent.EnvSubAgent")
async def test_execute_failure_with_error(mock_sub_agent_class, mock_validate, tool):
    mock_instance = mock_sub_agent_class.return_value
    mock_instance.run = AsyncMock(
        return_value={
            "status": "failed",
            "error": "API rate limit exceeded.",
            "state_summary": "- Environment API rate limit exceeded during inventory lookup.",
        }
    )

    result = await tool.execute(agent_query="Get history.")
    del result[
        "token_usage"
    ]  # Remove token usage for assertion since it's not relevant to this test

    assert result == {
        "status": "failed",
        "error": "API rate limit exceeded.",
        "summary": "- Environment API rate limit exceeded during inventory lookup.",
    }


@pytest.mark.asyncio
@patch.object(CallEnvSubAgentTool, "_validate_required_params")
@patch("app.services.env_sub_agent.EnvSubAgent")
async def test_execute_failure_fallback_error(mock_sub_agent_class, mock_validate, tool):
    mock_instance = mock_sub_agent_class.return_value
    mock_instance.run = AsyncMock(return_value={"status": "failed"})

    result = await tool.execute(agent_query="Get history.")
    del result[
        "token_usage"
    ]  # Remove token usage for assertion since it's not relevant to this test

    assert result == {
        "status": "failed",
        "error": "Sub-agent execution failed",
        "summary": "Sub-agent failed before generating a summary.",
    }
