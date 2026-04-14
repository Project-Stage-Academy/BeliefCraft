"""Tests for the agent API endpoint."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

from app.main import app
from app.models.responses import AgentRecommendationResponse, Recommendation
from fastapi.testclient import TestClient

client = TestClient(app)


def _structured_response() -> AgentRecommendationResponse:
    return AgentRecommendationResponse(
        request_id="test-123",
        query="Test warehouse query for analysis",
        task="Risk Assessment",
        analysis="Demand volatility is elevated for SKU-42.",
        algorithm="Algorithm 3.2 - (s,S) Policy",
        formulas=[],
        code_snippets=[],
        recommendations=[
            Recommendation(
                action="Increase reorder point by 10%",
                priority="high",
                rationale="Reduce stockout probability under higher variance",
            )
        ],
        citations=[],
        status="completed",
        confidence="high",
        reasoning_trace=[],
        iterations=2,
        token_usage={"test-model": {"total": 200}},
        execution_time_seconds=1.25,
        tools_used=["search_knowledge_base"],
        warnings=[],
        timestamp=datetime.now(UTC),
    )


@patch("app.api.v1.routes.agent.RecommendationGenerator")
@patch("app.api.v1.routes.agent.ReActAgent")
@patch("app.api.v1.routes.agent.get_skill_store")
def test_analyze_endpoint_success(
    mock_get_skill_store: MagicMock,
    mock_agent_class: MagicMock,
    mock_generator_class: MagicMock,
) -> None:
    """Analyze endpoint should return structured recommendation response."""
    final_state = {"request_id": "test-123", "status": "completed"}

    # Mock the skill store
    mock_store = MagicMock()
    mock_store.get_skill_catalog.return_value = "<skill>test</skill>"
    mock_store.get_skill_names.return_value = ["test"]
    mock_get_skill_store.return_value = mock_store

    mock_agent = mock_agent_class.return_value
    mock_agent.run = AsyncMock(return_value=final_state)

    mock_generator = mock_generator_class.return_value
    mock_generator.generate = AsyncMock(return_value=_structured_response())

    # We must explicitly inject the registry into the app state for the test
    # to pass the strict dependency injection check
    app.state.react_agent_registry = MagicMock()

    response = client.post(
        "/api/v1/agent/analyze",
        json={"query": "Test warehouse query for analysis", "max_iterations": 5},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["request_id"] == "test-123"
    assert data["status"] == "completed"
    assert data["task"] == "Risk Assessment"
    assert data["analysis"] == "Demand volatility is elevated for SKU-42."
    assert data["recommendations"][0]["priority"] == "high"
    assert "execution_time_seconds" in data

    mock_agent.run.assert_called_once_with(
        user_query="Test warehouse query for analysis",
        context={},
        max_iterations=5,
    )
    mock_generator.generate.assert_called_once_with(final_state)


@patch("app.api.v1.routes.agent.RecommendationGenerator")
@patch("app.api.v1.routes.agent.ReActAgent")
@patch("app.api.v1.routes.agent.get_skill_store")
def test_analyze_endpoint_with_context_and_default_iterations(
    mock_get_skill_store: MagicMock,
    mock_agent_class: MagicMock,
    mock_generator_class: MagicMock,
) -> None:
    """Analyze endpoint should forward context and default max_iterations."""
    final_state = {"request_id": "test-456", "status": "completed"}

    mock_get_skill_store.return_value = None

    mock_agent = mock_agent_class.return_value
    mock_agent.run = AsyncMock(return_value=final_state)

    mock_generator = mock_generator_class.return_value
    mock_generator.generate = AsyncMock(return_value=_structured_response())

    app.state.react_agent_registry = MagicMock()

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
@patch("app.api.v1.routes.agent.get_skill_store")
def test_analyze_endpoint_agent_error(
    mock_get_skill_store: MagicMock, mock_agent_class: MagicMock
) -> None:
    """Analyze endpoint should return 500 on agent execution failure."""
    mock_get_skill_store.return_value = None
    mock_agent = mock_agent_class.return_value
    mock_agent.run = AsyncMock(side_effect=Exception("Agent execution failed"))

    app.state.react_agent_registry = MagicMock()

    response = client.post(
        "/api/v1/agent/analyze",
        json={"query": "A valid query for testing"},
    )

    assert response.status_code == 500
    data = response.json()
    assert "Agent execution failed" in data["detail"]


@patch("app.api.v1.routes.agent.RecommendationGenerator")
@patch("app.api.v1.routes.agent.ReActAgent")
@patch("app.api.v1.routes.agent.get_skill_store")
def test_analyze_endpoint_generator_error(
    mock_get_skill_store: MagicMock,
    mock_agent_class: MagicMock,
    mock_generator_class: MagicMock,
) -> None:
    """Analyze endpoint should return 500 when recommendation generation fails."""
    mock_get_skill_store.return_value = None
    mock_agent = mock_agent_class.return_value
    mock_agent.run = AsyncMock(return_value={"request_id": "test-999"})

    mock_generator = mock_generator_class.return_value
    mock_generator.generate = AsyncMock(side_effect=Exception("Formatting failed"))

    app.state.react_agent_registry = MagicMock()

    response = client.post(
        "/api/v1/agent/analyze",
        json={"query": "A valid query for testing"},
    )

    assert response.status_code == 500
    data = response.json()
    assert "Formatting failed" in data["detail"]


def test_analyze_endpoint_missing_registry() -> None:
    """Analyze endpoint should return 500 if registry is not injected."""
    # Ensure registry is missing
    if hasattr(app.state, "react_agent_registry"):
        del app.state.react_agent_registry

    response = client.post(
        "/api/v1/agent/analyze",
        json={"query": "A valid query for testing"},
    )

    assert response.status_code == 500
    data = response.json()
    assert "ReAct tool registry not initialized" in data["detail"]
