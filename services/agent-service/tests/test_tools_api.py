"""Tests for the tools API endpoints."""

from typing import Any
from unittest.mock import patch

from app.main import app
from app.tools.base import BaseTool, ToolMetadata
from fastapi.testclient import TestClient

client = TestClient(app)


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
    """List all tools without filtering."""
    with patch("app.api.v1.routes.tools.tool_registry") as mock_registry:
        mock_tools = [
            MockTool("tool1", "environment", "Environment tool 1"),
            MockTool("tool2", "rag", "RAG tool 1"),
            MockTool("tool3", "environment", "Environment tool 2"),
        ]
        mock_registry.list_tools.return_value = mock_tools

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

        mock_registry.list_tools.assert_called_once_with(category=None)


def test_list_tools_filtered_by_category() -> None:
    """List tools filtered by category."""
    with patch("app.api.v1.routes.tools.tool_registry") as mock_registry:
        mock_tools = [
            MockTool("env_tool1", "environment", "Environment tool 1"),
            MockTool("env_tool2", "environment", "Environment tool 2"),
        ]
        mock_registry.list_tools.return_value = mock_tools

        response = client.get("/api/v1/tools?category=environment")

        assert response.status_code == 200
        data = response.json()
        assert data["total_count"] == 2
        assert len(data["tools"]) == 2

        # All tools should be in environment category
        for tool in data["tools"]:
            assert tool["category"] == "environment"

        mock_registry.list_tools.assert_called_once_with(category="environment")


def test_list_tools_empty_registry() -> None:
    """List tools when registry is empty."""
    with patch("app.api.v1.routes.tools.tool_registry") as mock_registry:
        mock_registry.list_tools.return_value = []

        response = client.get("/api/v1/tools")

        assert response.status_code == 200
        data = response.json()
        assert data["total_count"] == 0
        assert len(data["tools"]) == 0


def test_list_tools_parameters_structure() -> None:
    """Verify tool parameters schema is correctly returned."""
    with patch("app.api.v1.routes.tools.tool_registry") as mock_registry:
        mock_tool = MockTool("test_tool", "utility", "Test tool")
        mock_registry.list_tools.return_value = [mock_tool]

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
    """List tools when multiple categories exist."""
    with patch("app.api.v1.routes.tools.tool_registry") as mock_registry:
        mock_tools = [
            MockTool("env1", "environment", "Env tool"),
            MockTool("rag1", "rag", "RAG tool"),
            MockTool("plan1", "planning", "Planning tool"),
            MockTool("util1", "utility", "Utility tool"),
        ]
        mock_registry.list_tools.return_value = mock_tools

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
    with patch("app.api.v1.routes.tools.tool_registry") as mock_registry:
        mock_registry.list_tools.side_effect = RuntimeError("Registry unavailable")

        response = client.get("/api/v1/tools")

        assert response.status_code == 500
        data = response.json()
        assert "detail" in data
        assert "registry" in data["detail"].lower()
