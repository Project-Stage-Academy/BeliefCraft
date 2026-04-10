from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class AgentStep(BaseModel):
    """Single step in the agent's reasoning process"""

    step_number: int
    thought: str
    action: str
    action_input: dict[str, Any]
    observation: str


class AgentQueryResponse(BaseModel):
    """Response model for agent query"""

    request_id: str
    query: str
    status: str
    answer: str | None
    iterations: int
    total_tokens: int
    reasoning_trace: list[dict[str, Any]]
    duration_seconds: float


class ToolExecutionResponse(BaseModel):
    """Response model for tool execution"""

    tool_name: str
    result: Any
    execution_time_ms: float
    success: bool
    error: str | None = None


class ErrorResponse(BaseModel):
    """Error response model"""

    error: str
    message: str
    request_id: str | None = None
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class Citation(BaseModel):
    """
    Reference to a knowledge base chunk used in the recommendation.
    """

    model_config = ConfigDict(extra="forbid")

    chunk_id: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1, description="Section or algorithm title")
    page: int | None = Field(default=None, ge=1, description="Page number in source book")
    entity_type: str | None = Field(
        default=None, description="Entity type, e.g. text/formula/algorithm/table"
    )
    entity_number: str | None = Field(
        default=None, description="Entity number, e.g. 'Algorithm 3.2' or 'Formula 16.4'"
    )


class CodeSnippet(BaseModel):
    """
    Structured executable code snippet.
    """

    model_config = ConfigDict(extra="forbid")

    language: str = Field(default="python", min_length=1)
    code: str = Field(..., min_length=1, description="Code snippet body")
    description: str | None = Field(default=None, description="What the code does")
    dependencies: list[str] = Field(
        default_factory=list, description="Detected package dependencies"
    )
    validated: bool = Field(
        default=False,
        description=(
            "Whether automated syntax validation passed (AST parse only). "
            "Does not imply human review or semantic correctness."
        ),
    )


class Formula(BaseModel):
    """
    Mathematical formula in LaTeX with optional metadata.
    """

    model_config = ConfigDict(extra="forbid")

    latex: str = Field(..., min_length=1, description="LaTeX formatted formula")
    description: str | None = Field(default=None, description="Formula meaning")


class Recommendation(BaseModel):
    """
    Single actionable recommendation.
    """

    model_config = ConfigDict(extra="forbid")

    action: str = Field(..., min_length=1, description="Action to perform")
    priority: Literal["high", "medium", "low"] = Field(..., description="Recommendation priority")
    rationale: str = Field(..., min_length=1, description="Reason for this recommendation")
    expected_outcome: str | None = Field(default=None, description="Expected outcome")


class AgentRecommendationResponse(BaseModel):
    """
    Structured recommendation response for warehouse operations.

    Includes extracted formulas, code snippets, citations, and actionable steps.
    """

    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(..., min_length=1)
    query: str = Field(..., min_length=1)
    final_answer: str | None = Field(default=None, description="Raw final answer from the agent")

    task: str = Field(..., min_length=1, description="High-level task identified")
    analysis: str = Field(..., min_length=1, description="Agent analysis summary")

    algorithm: str | None = Field(
        default=None, description="Algorithm name or number if identified"
    )
    formulas: list[Formula] = Field(default_factory=list)
    code_snippets: list[CodeSnippet] = Field(default_factory=list)

    recommendations: list[Recommendation] = Field(default_factory=list)

    citations: list[Citation] = Field(default_factory=list)

    status: Literal["completed", "partial", "failed", "max_iterations"] = Field(
        ..., description="Recommendation generation status"
    )
    confidence: Literal["high", "medium", "low"] | None = Field(
        default=None, description="Confidence level"
    )
    reasoning_trace: list[dict[str, Any]] = Field(default_factory=list)

    iterations: int = Field(..., ge=0)
    total_tokens: int = Field(..., ge=0)
    cache_read_input_tokens: int = Field(..., ge=0)
    cache_creation_input_tokens: int = Field(..., ge=0)
    execution_time_seconds: float = Field(..., ge=0.0)
    tools_used: list[str] = Field(default_factory=list)

    warnings: list[str] = Field(default_factory=list, description="Potential issues/limitations")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
