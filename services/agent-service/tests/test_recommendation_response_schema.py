"""
Tests for structured recommendation response schema.
"""

from app.models.responses import AgentRecommendationResponse, CodeSnippet
from pydantic import ValidationError


def _base_payload() -> dict:
    return {
        "request_id": "req-123",
        "query": "How should we reduce stockout risk this week?",
        "task": "Inventory Risk Mitigation",
        "analysis": "Current inventory risk is elevated for high-turnover SKUs.",
        "recommendations": [
            {
                "action": "Increase reorder point for SKU-A by 15%",
                "priority": "high",
                "rationale": "Demand variance increased while lead time widened.",
                "expected_outcome": "Lower stockout probability within 7 days",
            }
        ],
        "status": "completed",
        "iterations": 3,
        "total_tokens": 1200,
        "execution_time_seconds": 2.41,
    }


def test_structured_response_accepts_valid_payload() -> None:
    payload = _base_payload()
    payload["code_snippets"] = [
        {
            "language": "python",
            "code": "import math\nx = math.sqrt(16)\nprint(x)\n",
            "validated": False,
        }
    ]

    response = AgentRecommendationResponse(**payload)

    assert response.request_id == "req-123"
    assert len(response.recommendations) == 1
    assert response.code_snippets[0].validated is True


def test_structured_response_rejects_invalid_python_syntax() -> None:
    payload = _base_payload()
    payload["code_snippets"] = [
        CodeSnippet(
            language="python",
            code="def broken(:\n    pass\n",
            validated=False,
        )
    ]

    try:
        AgentRecommendationResponse(**payload)
        raise AssertionError("Expected ValidationError was not raised")
    except ValidationError as exc:
        assert "Invalid Python syntax in code snippet" in str(exc)


def test_structured_response_requires_recommendations() -> None:
    payload = _base_payload()
    payload["recommendations"] = []

    try:
        AgentRecommendationResponse(**payload)
        raise AssertionError("Expected ValidationError was not raised")
    except ValidationError as exc:
        assert "at least 1 item" in str(exc)


def test_recommendation_priority_is_constrained() -> None:
    payload = _base_payload()
    payload["recommendations"][0]["priority"] = "urgent"

    try:
        AgentRecommendationResponse(**payload)
        raise AssertionError("Expected ValidationError was not raised")
    except ValidationError as exc:
        assert "high" in str(exc) and "medium" in str(exc) and "low" in str(exc)
