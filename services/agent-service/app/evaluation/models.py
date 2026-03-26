"""Pydantic models for agent evaluation framework."""

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class ExpectedOutput(BaseModel):
    """Expected output criteria for evaluation scenario."""

    must_include: dict[str, Any] = Field(
        default_factory=dict,
        description="Required elements (algorithm, formula, code, recommendations, etc.)",
    )
    must_cite: dict[str, Any] = Field(
        default_factory=dict,
        description="Required citation criteria (chapters, entity types, etc.)",
    )


class EvaluationScenario(BaseModel):
    """Test scenario for agent evaluation."""

    id: str = Field(..., description="Unique scenario identifier")
    category: str = Field(..., description="Scenario category (e.g., inventory_replenishment)")
    query: str = Field(..., description="User query to test", min_length=10)
    context: dict[str, Any] = Field(default_factory=dict, description="Additional context")
    max_iterations: int = Field(default=3, ge=1, le=10, description="Max iterations for agent")

    expected_output: ExpectedOutput = Field(..., description="Expected output criteria")

    evaluation_criteria: dict[str, str] = Field(
        default_factory=dict,
        description="Human-readable evaluation criteria descriptions",
    )
    difficulty: Literal["easy", "medium", "hard"] = Field(..., description="Scenario difficulty")


class EvaluationResult(BaseModel):
    """Result of evaluating a single scenario."""

    scenario_id: str
    scenario_category: str
    query: str
    difficulty: Literal["easy", "medium", "hard"]

    agent_status: str
    iterations: int
    execution_time_seconds: float

    retrieval_accuracy: float = Field(..., ge=0.0, le=1.0)
    citation_quality: float = Field(..., ge=0.0, le=1.0)
    code_validity: float = Field(..., ge=0.0, le=1.0)
    reasoning_quality: float = Field(..., ge=0.0, le=1.0)
    actionability: float = Field(..., ge=0.0, le=1.0)

    overall_score: float = Field(..., ge=0.0, le=1.0, description="Weighted average of metrics")

    passed: bool
    failure_reasons: list[str] = Field(default_factory=list)

    algorithm_found: str | None = None
    citations_count: int = Field(default=0, ge=0)
    code_snippets_count: int = Field(default=0, ge=0)
    recommendations_count: int = Field(default=0, ge=0)
    tools_used: list[str] = Field(default_factory=list)

    full_response: dict[str, Any] = Field(default_factory=dict)

    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class CategoryStats(BaseModel):
    """Statistics for a specific category."""

    total: int = Field(..., ge=0)
    passed: int = Field(..., ge=0)
    pass_rate: float = Field(..., ge=0.0, le=1.0)
    avg_score: float = Field(..., ge=0.0, le=1.0)


class EvaluationReport(BaseModel):
    """Aggregated report of evaluation run."""

    report_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

    total_scenarios: int = Field(..., ge=0)
    passed: int = Field(..., ge=0)
    failed: int = Field(..., ge=0)
    pass_rate: float = Field(..., ge=0.0, le=1.0)

    avg_retrieval_accuracy: float = Field(..., ge=0.0, le=1.0)
    avg_citation_quality: float = Field(..., ge=0.0, le=1.0)
    avg_code_validity: float = Field(..., ge=0.0, le=1.0)
    avg_reasoning_quality: float = Field(..., ge=0.0, le=1.0)
    avg_actionability: float = Field(..., ge=0.0, le=1.0)
    avg_overall_score: float = Field(..., ge=0.0, le=1.0)

    avg_execution_time: float = Field(..., ge=0.0)
    avg_iterations: float = Field(..., ge=0.0)

    results_by_category: dict[str, CategoryStats] = Field(default_factory=dict)
    results_by_difficulty: dict[str, CategoryStats] = Field(default_factory=dict)

    failed_scenarios: list[str] = Field(default_factory=list)
    results: list[EvaluationResult] = Field(default_factory=list)
