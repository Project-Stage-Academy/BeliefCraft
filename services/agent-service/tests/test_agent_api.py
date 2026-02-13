"""Tests for the agent API endpoints."""

from unittest.mock import AsyncMock, MagicMock, patch

from app.main import app
from app.models.agent_state import ThoughtStep, ToolCall
from fastapi.testclient import TestClient

client = TestClient(app)


@patch("app.api.v1.routes.agent.ReActAgent")
def test_analyze_endpoint_success(mock_agent_class: MagicMock) -> None:
    """Analyze endpoint should return structured response."""
    mock_agent = mock_agent_class.return_value
    mock_agent.run = AsyncMock(
        return_value={
            "request_id": "test-123",
            "user_query": "Test query",
            "iteration": 2,
            "thoughts": [],
            "tool_calls": [],
            "final_answer": "Test answer",
            "status": "completed",
            "total_tokens": 200,
        }
    )

    response = client.post(
        "/api/v1/agent/analyze",
        json={"query": "Test warehouse query for analysis", "max_iterations": 5},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert data["answer"] == "Test answer"
    assert "reasoning_trace" in data
    assert data["request_id"] == "test-123"
    assert data["iterations"] == 2
    assert data["total_tokens"] == 200


@patch("app.api.v1.routes.agent.ReActAgent")
def test_analyze_endpoint_with_context(mock_agent_class: MagicMock) -> None:
    """Analyze endpoint should forward context to the agent."""
    mock_agent = mock_agent_class.return_value
    mock_agent.run = AsyncMock(
        return_value={
            "request_id": "test-456",
            "user_query": "Check stock levels",
            "iteration": 1,
            "thoughts": [],
            "tool_calls": [],
            "final_answer": "Stock is at 500 units",
            "status": "completed",
            "total_tokens": 100,
        }
    )

    response = client.post(
        "/api/v1/agent/analyze",
        json={
            "query": "Check stock levels for warehouse",
            "context": {"warehouse_id": "WH-001"},
        },
    )

    assert response.status_code == 200
    mock_agent.run.assert_called_once_with(
        user_query="Check stock levels for warehouse",
        context={"warehouse_id": "WH-001"},
        max_iterations=10,
    )


def test_analyze_endpoint_validation_query_too_short() -> None:
    """Analyze endpoint should reject queries shorter than 10 characters."""
    response = client.post(
        "/api/v1/agent/analyze",
        json={"query": "short"},
    )
    assert response.status_code == 422


def test_analyze_endpoint_validation_missing_query() -> None:
    """Analyze endpoint should reject requests without a query."""
    response = client.post(
        "/api/v1/agent/analyze",
        json={},
    )
    assert response.status_code == 422


def test_analyze_endpoint_validation_max_iterations_bounds() -> None:
    """Analyze endpoint should reject max_iterations outside [1, 20]."""
    response = client.post(
        "/api/v1/agent/analyze",
        json={"query": "A valid query for testing", "max_iterations": 0},
    )
    assert response.status_code == 422

    response = client.post(
        "/api/v1/agent/analyze",
        json={"query": "A valid query for testing", "max_iterations": 21},
    )
    assert response.status_code == 422


@patch("app.api.v1.routes.agent.ReActAgent")
def test_analyze_endpoint_agent_error(mock_agent_class: MagicMock) -> None:
    """Analyze endpoint should return 500 on agent execution failure."""
    mock_agent = mock_agent_class.return_value
    mock_agent.run = AsyncMock(side_effect=Exception("Agent execution failed"))

    response = client.post(
        "/api/v1/agent/analyze",
        json={"query": "A valid query for testing"},
    )

    assert response.status_code == 500
    data = response.json()
    assert "Agent execution failed" in data["detail"]


@patch("app.api.v1.routes.agent.ReActAgent")
def test_analyze_endpoint_response_includes_duration(mock_agent_class: MagicMock) -> None:
    """Response should include duration_seconds field."""
    mock_agent = mock_agent_class.return_value
    mock_agent.run = AsyncMock(
        return_value={
            "request_id": "test-789",
            "user_query": "Test query",
            "iteration": 1,
            "thoughts": [],
            "tool_calls": [],
            "final_answer": "Quick answer",
            "status": "completed",
            "total_tokens": 50,
        }
    )

    response = client.post(
        "/api/v1/agent/analyze",
        json={"query": "A valid query for testing"},
    )

    assert response.status_code == 200
    data = response.json()
    assert "duration_seconds" in data
    assert isinstance(data["duration_seconds"], float)


@patch("app.api.v1.routes.agent.ReActAgent")
def test_analyze_endpoint_includes_final_thought_in_trace(mock_agent_class: MagicMock) -> None:
    """Reasoning trace must include thoughts that have no matching tool call."""
    thought_1 = ThoughtStep(thought="Let me search", next_action="tool_use")
    thought_2 = ThoughtStep(thought="Now I have the answer", next_action="answer")
    tool_call = ToolCall(
        tool_name="search",
        arguments={"q": "test"},
        result={"count": 5},
    )
    mock_agent = mock_agent_class.return_value
    mock_agent.run = AsyncMock(
        return_value={
            "request_id": "test-trace",
            "user_query": "Test query",
            "iteration": 1,
            "thoughts": [thought_1, thought_2],
            "tool_calls": [tool_call],
            "final_answer": "The answer",
            "status": "completed",
            "total_tokens": 100,
        }
    )

    response = client.post(
        "/api/v1/agent/analyze",
        json={"query": "A valid query for testing"},
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data["reasoning_trace"]) == 2
    # First entry has both thought and action
    assert "action" in data["reasoning_trace"][0]
    assert data["reasoning_trace"][0]["thought"] == "Let me search"
    # Second entry has thought but no action
    assert "action" not in data["reasoning_trace"][1]
    assert data["reasoning_trace"][1]["thought"] == "Now I have the answer"
