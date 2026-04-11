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
        "cache_read_input_tokens": 0,
        "cache_creation_input_tokens": 0,
        "execution_time_seconds": 2.41,
    }


def test_structured_response_accepts_valid_payload() -> None:
    payload = _base_payload()
    payload["final_answer"] = (
        "## Inventory Risk Mitigation\n\n### Analysis\nCurrent inventory risk is elevated."
    )
    payload["code_snippets"] = [
        {
            "language": "python",
            "code": "import math\nx = math.sqrt(16)\nprint(x)\n",
            "validated": True,
        }
    ]

    response = AgentRecommendationResponse(**payload)

    assert response.request_id == "req-123"
    assert len(response.recommendations) == 1
    assert response.code_snippets[0].validated is True
    assert response.final_answer == payload["final_answer"]


def test_structured_response_trusts_extractor_managed_validation_flag() -> None:
    payload = _base_payload()
    payload["code_snippets"] = [
        CodeSnippet(
            language="python",
            code="def broken(:\n    pass\n",
            validated=False,
        )
    ]

    response = AgentRecommendationResponse(**payload)

    assert len(response.code_snippets) == 1
    assert response.code_snippets[0].language == "python"
    assert response.code_snippets[0].validated is False


def test_structured_response_accepts_empty_recommendations() -> None:
    payload = _base_payload()
    payload["recommendations"] = []

    response = AgentRecommendationResponse(**payload)

    assert response.recommendations == []


def test_structured_response_accepts_missing_final_answer() -> None:
    payload = _base_payload()

    response = AgentRecommendationResponse(**payload)

    assert response.final_answer is None


def test_recommendation_priority_is_constrained() -> None:
    payload = _base_payload()
    payload["recommendations"][0]["priority"] = "urgent"

    try:
        AgentRecommendationResponse(**payload)
        raise AssertionError("Expected ValidationError was not raised")
    except ValidationError as exc:
        assert "high" in str(exc) and "medium" in str(exc) and "low" in str(exc)
