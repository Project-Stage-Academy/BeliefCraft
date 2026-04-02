# file: services/agent-service/tests/test_tools_api.py
"""Tests for the tools API endpoints."""

from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock

import pytest
from app.main import app
from app.tools.base import BaseTool, ToolMetadata
from fastapi.testclient import TestClient

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_app_state() -> Generator[None, None, None]:
    """Ensure app.state is clean before and after each test."""
    # Backup existing state
    old_react = getattr(app.state, "react_agent_registry", None)
    old_env = getattr(app.state, "env_sub_agent_registry", None)

    yield

    # Restore state
    if old_react is not None:
        app.state.react_agent_registry = old_react
    elif hasattr(app.state, "react_agent_registry"):
        delattr(app.state, "react_agent_registry")

    if old_env is not None:
        app.state.env_sub_agent_registry = old_env
    elif hasattr(app.state, "env_sub_agent_registry"):
        delattr(app.state, "env_sub_agent_registry")


class MockTool(BaseTool):
    """Mock tool for testing."""

    def __init__(self, name: str, category: str, description: str):
        self._name = name
        self._category = category
        self._description = description
        super().__init__()

    def get_metadata(self) -> ToolMetadata:
        """Return tool metadata."""
        return ToolMetadata(
            name=self._name,
            description=self._description,
            category=self._category,
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Query parameter",
                    }
                },
                "required": ["query"],
            },
        )

    async def execute(self, **kwargs: Any) -> dict[str, str]:
        """Execute mock tool."""
        return {"result": "mock"}


def test_list_tools_all() -> None:
    """List all tools without filtering from both registries."""
    mock_react = MagicMock()
    mock_react.list_tools.return_value = [
        MockTool("tool1", "environment", "Environment tool 1"),
        MockTool("tool2", "rag", "RAG tool 1"),
    ]
    app.state.react_agent_registry = mock_react

    mock_env = MagicMock()
    mock_env.list_tools.return_value = [
        MockTool("tool3", "environment", "Environment tool 2"),
    ]
    app.state.env_sub_agent_registry = mock_env

    response = client.get("/api/v1/tools")

    assert response.status_code == 200
    data = response.json()
    assert data["total_count"] == 3
    assert len(data["tools"]) == 3

    # Verify tool structure
    tool = data["tools"][0]
    assert "name" in tool
    assert "description" in tool
    assert "category" in tool
    assert "parameters" in tool

    mock_react.list_tools.assert_called_once_with(category=None)
    mock_env.list_tools.assert_called_once_with(category=None)


def test_list_tools_filtered_by_category() -> None:
    """List tools filtered by category."""
    mock_react = MagicMock()
    mock_react.list_tools.return_value = []
    app.state.react_agent_registry = mock_react

    mock_env = MagicMock()
    mock_env.list_tools.return_value = [
        MockTool("env_tool1", "environment", "Environment tool 1"),
        MockTool("env_tool2", "environment", "Environment tool 2"),
    ]
    app.state.env_sub_agent_registry = mock_env

    response = client.get("/api/v1/tools?category=environment")

    assert response.status_code == 200
    data = response.json()
    assert data["total_count"] == 2
    assert len(data["tools"]) == 2

    # All tools should be in environment category
    for tool in data["tools"]:
        assert tool["category"] == "environment"

    mock_react.list_tools.assert_called_once_with(category="environment")
    mock_env.list_tools.assert_called_once_with(category="environment")


def test_list_tools_empty_registry() -> None:
    """List tools when both registries return empty."""
    mock_react = MagicMock()
    mock_react.list_tools.return_value = []
    app.state.react_agent_registry = mock_react

    mock_env = MagicMock()
    mock_env.list_tools.return_value = []
    app.state.env_sub_agent_registry = mock_env

    response = client.get("/api/v1/tools")

    assert response.status_code == 200
    data = response.json()
    assert data["total_count"] == 0
    assert len(data["tools"]) == 0


def test_list_tools_parameters_structure() -> None:
    """Verify tool parameters schema is correctly returned."""
    mock_react = MagicMock()
    mock_tool = MockTool("test_tool", "utility", "Test tool")
    mock_react.list_tools.return_value = [mock_tool]
    app.state.react_agent_registry = mock_react
    app.state.env_sub_agent_registry = None

    response = client.get("/api/v1/tools")

    assert response.status_code == 200
    data = response.json()
    tool = data["tools"][0]

    # Verify parameter schema structure
    params = tool["parameters"]
    assert params["type"] == "object"
    assert "properties" in params
    assert "query" in params["properties"]
    assert params["properties"]["query"]["type"] == "string"
    assert "required" in params


def test_list_tools_multiple_categories() -> None:
    """List tools when multiple categories exist across registries."""
    mock_react = MagicMock()
    mock_react.list_tools.return_value = [
        MockTool("rag1", "rag", "RAG tool"),
        MockTool("plan1", "planning", "Planning tool"),
        MockTool("util1", "utility", "Utility tool"),
    ]
    app.state.react_agent_registry = mock_react

    mock_env = MagicMock()
    mock_env.list_tools.return_value = [
        MockTool("env1", "environment", "Env tool"),
    ]
    app.state.env_sub_agent_registry = mock_env

    response = client.get("/api/v1/tools")

    assert response.status_code == 200
    data = response.json()
    assert data["total_count"] == 4

    # Verify all categories are present
    categories = {tool["category"] for tool in data["tools"]}
    assert categories == {"environment", "rag", "planning", "utility"}


def test_list_tools_invalid_category() -> None:
    """Invalid category value must return 422 Unprocessable Entity."""
    response = client.get("/api/v1/tools?category=invalid_category")

    assert response.status_code == 422
    data = response.json()
    # FastAPI returns 'detail' with validation errors
    assert "detail" in data


def test_list_tools_registry_failure() -> None:
    """Registry failure must return 500 with a descriptive error message."""
    mock_react = MagicMock()
    mock_react.list_tools.side_effect = RuntimeError("Registry unavailable")
    app.state.react_agent_registry = mock_react
    app.state.env_sub_agent_registry = None

    response = client.get("/api/v1/tools")

    assert response.status_code == 500
    data = response.json()
    assert "detail" in data
    assert "registry" in data["detail"].lower()


def test_list_tools_missing_registries() -> None:
    """Should return 500 if both registries are entirely missing from app.state."""
    app.state.react_agent_registry = None
    app.state.env_sub_agent_registry = None

    response = client.get("/api/v1/tools")

    assert response.status_code == 500
    data = response.json()
    assert "detail" in data
    assert "registry" in data["detail"].lower()
