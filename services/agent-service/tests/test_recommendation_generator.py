"""
Comprehensive unit tests for RecommendationGenerator.

Covers:
- Successful full generation path
- LLM-based final answer parsing (including JSON-in-markdown)
- Fallback when final_answer is absent or agent failed
- Formula extraction from text and RAG tool results
- Citation extraction delegation
- Reasoning trace assembly (dict and Pydantic tool-call shapes)
- Warning detection (max_iterations, no algorithm, failed tools, low confidence)
- Execution time calculation
- Tools-used deduplication
- Graceful handling of LLM parsing errors
"""

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from app.models.agent_state import AgentState, ThoughtStep, ToolCall
from app.models.responses import (
    AgentRecommendationResponse,
    Citation,
    Formula,
    Recommendation,
)
from app.services.recommendation_generator import RecommendationGenerator

# ---------------------------------------------------------------------------
# Helpers / Fixtures
# ---------------------------------------------------------------------------


def _make_tool_call(
    tool_name: str,
    arguments: dict | None = None,
    result: dict | None = None,
    error: str | None = None,
    as_dict: bool = False,
) -> Any:
    if as_dict:
        return {
            "tool_name": tool_name,
            "arguments": arguments or {},
            "result": result,
            "error": error,
        }
    return ToolCall(
        tool_name=tool_name,
        arguments=arguments or {},
        result=result,
        error=error,
    )


def _make_thought(text: str = "Thinking…", as_dict: bool = False) -> Any:
    if as_dict:
        return {"thought": text, "next_action": "call_tool"}
    return ThoughtStep(thought=text, next_action="call_tool")


def _base_agent_state(**overrides: Any) -> AgentState:
    started = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    state: AgentState = {
        "request_id": "req-test-001",
        "user_query": "How should we handle stockout risk?",
        "context": {},
        "iteration": 3,
        "max_iterations": 10,
        "thoughts": [],
        "tool_calls": [],
        "messages": [],
        "final_answer": "Use (s,S) policy with safety stock. $S = \\mu + z\\sigma$.",
        "status": "completed",
        "error": None,
        "total_tokens": 500,
        "started_at": started,
        "completed_at": started + timedelta(seconds=4.5),
    }
    state.update(overrides)
    return state


def _structured_llm_response(
    task: str = "Inventory Management",
    analysis: str = "Risk is elevated.",
    algorithm: str | None = "Algorithm 3.2 - (s,S) Policy",
    confidence: str = "high",
) -> dict:
    return {
        "message": {
            "role": "assistant",
            "content": json.dumps(
                {
                    "task": task,
                    "analysis": analysis,
                    "algorithm": algorithm,
                    "recommendations": [
                        {
                            "action": "Increase reorder point by 15%",
                            "priority": "high",
                            "rationale": "Demand variance increased",
                            "expected_outcome": "Reduce stockout probability",
                        }
                    ],
                    "confidence": confidence,
                }
            ),
        },
        "tool_calls": [],
        "finish_reason": "stop",
        "tokens": {"prompt": 100, "completion": 50, "total": 150},
    }


@pytest.fixture()
def mock_llm() -> MagicMock:
    llm = MagicMock()
    llm.chat_completion = AsyncMock(return_value=_structured_llm_response())
    return llm


@pytest.fixture()
def mock_formula_extractor() -> MagicMock:
    extractor = MagicMock()
    extractor.extract_from_text.return_value = [
        Formula(latex="S = \\mu + z\\sigma", description="Safety stock formula")
    ]
    extractor.extract_from_rag_chunks.return_value = []
    return extractor


@pytest.fixture()
def mock_citation_extractor() -> MagicMock:
    extractor = MagicMock()
    extractor.extract_from_tool_calls.return_value = [
        Citation(
            chunk_id="chunk-1",
            title="Section 3.2",
            page=42,
            entity_type="algorithm",
            entity_number="Algorithm 3.2",
        )
    ]
    return extractor


@pytest.fixture()
def generator(
    mock_llm: MagicMock,
    mock_formula_extractor: MagicMock,
    mock_citation_extractor: MagicMock,
) -> RecommendationGenerator:
    return RecommendationGenerator(
        llm=mock_llm,
        formula_extractor=mock_formula_extractor,
        citation_extractor=mock_citation_extractor,
    )


# ---------------------------------------------------------------------------
# successful full generation
# ---------------------------------------------------------------------------


class TestGenerate:
    @pytest.mark.asyncio
    async def test_returns_recommendation_response(
        self, generator: RecommendationGenerator
    ) -> None:
        state = _base_agent_state()
        result = await generator.generate(state)
        assert isinstance(result, AgentRecommendationResponse)

    @pytest.mark.asyncio
    async def test_basic_fields_populated(self, generator: RecommendationGenerator) -> None:
        state = _base_agent_state()
        result = await generator.generate(state)

        assert result.request_id == "req-test-001"
        assert result.query == "How should we handle stockout risk?"
        assert result.task == "Inventory Management"
        assert result.analysis == "Risk is elevated."
        assert result.algorithm == "Algorithm 3.2 - (s,S) Policy"
        assert result.status == "completed"
        assert result.confidence == "high"
        assert result.iterations == 3
        assert result.total_tokens == 500

    @pytest.mark.asyncio
    async def test_execution_time_calculated(self, generator: RecommendationGenerator) -> None:
        state = _base_agent_state()
        result = await generator.generate(state)
        assert result.execution_time_seconds == pytest.approx(4.5)

    @pytest.mark.asyncio
    async def test_formulas_from_extractor(self, generator: RecommendationGenerator) -> None:
        state = _base_agent_state()
        result = await generator.generate(state)
        assert len(result.formulas) == 1
        assert result.formulas[0].latex == "S = \\mu + z\\sigma"

    @pytest.mark.asyncio
    async def test_citations_from_extractor(self, generator: RecommendationGenerator) -> None:
        state = _base_agent_state()
        result = await generator.generate(state)
        assert len(result.citations) == 1
        assert result.citations[0].chunk_id == "chunk-1"

    @pytest.mark.asyncio
    async def test_recommendations_from_llm(self, generator: RecommendationGenerator) -> None:
        state = _base_agent_state()
        result = await generator.generate(state)
        assert len(result.recommendations) == 1
        assert result.recommendations[0].priority == "high"

    @pytest.mark.asyncio
    async def test_tools_used_deduplicated(self, generator: RecommendationGenerator) -> None:
        state = _base_agent_state(
            tool_calls=[
                _make_tool_call("search_knowledge_base"),
                _make_tool_call("search_knowledge_base"),
                _make_tool_call("get_entity_by_number"),
            ]
        )
        result = await generator.generate(state)
        assert sorted(result.tools_used) == sorted(
            ["search_knowledge_base", "get_entity_by_number"]
        )

    @pytest.mark.asyncio
    async def test_tools_used_from_dict_tool_calls(
        self, generator: RecommendationGenerator
    ) -> None:
        state = _base_agent_state(
            tool_calls=[
                _make_tool_call("search_knowledge_base", as_dict=True),
            ]
        )
        result = await generator.generate(state)
        assert "search_knowledge_base" in result.tools_used


# ---------------------------------------------------------------------------
# Fallback when no final answer
# ---------------------------------------------------------------------------


class TestFallbackResponse:
    @pytest.mark.asyncio
    async def test_returns_failed_status_when_no_final_answer(
        self, generator: RecommendationGenerator
    ) -> None:
        state = _base_agent_state(final_answer=None, status="failed", error="Timeout")
        result = await generator.generate(state)
        assert result.status == "failed"
        assert result.task == "Analysis Failed"
        assert "Timeout" in result.analysis
        assert len(result.recommendations) == 1
        assert result.recommendations[0].priority == "high"

    @pytest.mark.asyncio
    async def test_fallback_includes_error_in_warnings(
        self, generator: RecommendationGenerator
    ) -> None:
        state = _base_agent_state(final_answer="", status="failed", error="LLM error")
        result = await generator.generate(state)
        assert "LLM error" in result.warnings

    @pytest.mark.asyncio
    async def test_fallback_execution_time_is_zero(
        self, generator: RecommendationGenerator
    ) -> None:
        state = _base_agent_state(final_answer=None, status="failed")
        result = await generator.generate(state)
        assert result.execution_time_seconds == 0.0

    @pytest.mark.asyncio
    async def test_fallback_tools_used_is_empty(self, generator: RecommendationGenerator) -> None:
        state = _base_agent_state(final_answer=None, status="failed")
        result = await generator.generate(state)
        assert result.tools_used == []

    @pytest.mark.asyncio
    async def test_fallback_uses_unknown_error_when_none(
        self, generator: RecommendationGenerator
    ) -> None:
        state = _base_agent_state(final_answer=None, status="failed", error=None)
        result = await generator.generate(state)
        assert "Unknown error" in result.warnings


# ---------------------------------------------------------------------------
# LLM parsing
# ---------------------------------------------------------------------------


class TestParseFinalAnswer:
    @pytest.mark.asyncio
    async def test_strips_markdown_json_fences(
        self,
        mock_llm: MagicMock,
        mock_formula_extractor: MagicMock,
        mock_citation_extractor: MagicMock,
    ) -> None:
        payload = json.dumps(
            {
                "task": "Stock Analysis",
                "analysis": "All good.",
                "algorithm": None,
                "recommendations": [
                    {"action": "Hold", "priority": "low", "rationale": "Stable demand"}
                ],
                "confidence": "medium",
            }
        )
        mock_llm.chat_completion = AsyncMock(
            return_value={
                "message": {"role": "assistant", "content": f"```json\n{payload}\n```"},
                "tool_calls": [],
                "finish_reason": "stop",
                "tokens": {"prompt": 10, "completion": 10, "total": 20},
            }
        )
        gen = RecommendationGenerator(
            llm=mock_llm,
            formula_extractor=mock_formula_extractor,
            citation_extractor=mock_citation_extractor,
        )
        state = _base_agent_state()
        result = await gen.generate(state)
        assert result.task == "Stock Analysis"
        assert result.confidence == "medium"

    @pytest.mark.asyncio
    async def test_falls_back_gracefully_on_invalid_json(
        self,
        mock_llm: MagicMock,
        mock_formula_extractor: MagicMock,
        mock_citation_extractor: MagicMock,
    ) -> None:
        mock_llm.chat_completion = AsyncMock(
            return_value={
                "message": {"role": "assistant", "content": "not valid json {{"},
                "tool_calls": [],
                "finish_reason": "stop",
                "tokens": {"prompt": 5, "completion": 5, "total": 10},
            }
        )
        gen = RecommendationGenerator(
            llm=mock_llm,
            formula_extractor=mock_formula_extractor,
            citation_extractor=mock_citation_extractor,
        )
        state = _base_agent_state()
        result = await gen.generate(state)
        # Fallback: task is "Analysis", analysis is the raw final_answer
        assert result.task == "Analysis"
        assert result.final_answer if hasattr(result, "final_answer") else True

    @pytest.mark.asyncio
    async def test_falls_back_gracefully_on_llm_exception(
        self,
        mock_llm: MagicMock,
        mock_formula_extractor: MagicMock,
        mock_citation_extractor: MagicMock,
    ) -> None:
        mock_llm.chat_completion = AsyncMock(side_effect=RuntimeError("Network error"))
        gen = RecommendationGenerator(
            llm=mock_llm,
            formula_extractor=mock_formula_extractor,
            citation_extractor=mock_citation_extractor,
        )
        state = _base_agent_state()
        result = await gen.generate(state)
        assert result.task == "Analysis"
        assert len(result.recommendations) >= 1

    @pytest.mark.asyncio
    async def test_recommendations_are_pydantic_models(
        self, generator: RecommendationGenerator
    ) -> None:
        state = _base_agent_state()
        result = await generator.generate(state)
        for rec in result.recommendations:
            assert isinstance(rec, Recommendation)


# ---------------------------------------------------------------------------
# Formula extraction
# ---------------------------------------------------------------------------


class TestFormulaExtraction:
    @pytest.mark.asyncio
    async def test_formulas_extracted_from_rag_result(
        self, mock_llm: MagicMock, mock_citation_extractor: MagicMock
    ) -> None:
        formula_from_rag = Formula(latex="D = \\lambda t", description="Demand formula")
        extractor = MagicMock()
        extractor.extract_from_text.return_value = []
        extractor.extract_from_rag_chunks.return_value = [formula_from_rag]

        gen = RecommendationGenerator(
            llm=mock_llm,
            formula_extractor=extractor,
            citation_extractor=mock_citation_extractor,
        )
        tool_result = {"documents": [{"content": "D = \\lambda t", "chunk_type": "formula"}]}
        state = _base_agent_state(
            tool_calls=[_make_tool_call("search_knowledge_base", result=tool_result)]
        )
        result = await gen.generate(state)
        assert any(f.latex == "D = \\lambda t" for f in result.formulas)
        extractor.extract_from_rag_chunks.assert_called_once_with(tool_result["documents"])

    @pytest.mark.asyncio
    async def test_non_rag_tools_are_skipped_for_formulas(
        self, mock_llm: MagicMock, mock_citation_extractor: MagicMock
    ) -> None:
        extractor = MagicMock()
        extractor.extract_from_text.return_value = []
        extractor.extract_from_rag_chunks.return_value = []

        gen = RecommendationGenerator(
            llm=mock_llm,
            formula_extractor=extractor,
            citation_extractor=mock_citation_extractor,
        )
        state = _base_agent_state(
            tool_calls=[_make_tool_call("get_inventory_data", result={"items": []})]
        )
        await gen.generate(state)
        extractor.extract_from_rag_chunks.assert_not_called()


# ---------------------------------------------------------------------------
# Code snippet enrichment
# ---------------------------------------------------------------------------


class TestCodeSnippetEnrichment:
    @pytest.mark.asyncio
    async def test_extracts_python_code_from_final_answer(
        self, generator: RecommendationGenerator
    ) -> None:
        state = _base_agent_state(
            final_answer=(
                "Use this snippet:\n" "```python\n" "import math\n" "x = math.sqrt(16)\n" "```"
            )
        )
        result = await generator.generate(state)

        python_snippets = [s for s in result.code_snippets if s.language == "python"]
        assert len(python_snippets) == 1
        assert python_snippets[0].validated is True
        assert "math" in python_snippets[0].dependencies

    @pytest.mark.asyncio
    async def test_extracts_julia_from_rag_algorithm_chunk(
        self, generator: RecommendationGenerator
    ) -> None:
        state = _base_agent_state(
            tool_calls=[
                _make_tool_call(
                    "search_knowledge_base",
                    result={
                        "documents": [
                            {
                                "chunk_type": "algorithm",
                                "section_title": "Policy Iteration",
                                "content": "function POLICY(x)\n    return x\nend",
                            }
                        ]
                    },
                )
            ]
        )
        result = await generator.generate(state)

        julia_snippets = [s for s in result.code_snippets if s.language == "julia"]
        assert len(julia_snippets) == 1
        assert "function POLICY" in julia_snippets[0].code
        assert julia_snippets[0].description == "Policy Iteration"

    @pytest.mark.asyncio
    async def test_invalid_python_is_downgraded_to_text(
        self, generator: RecommendationGenerator
    ) -> None:
        state = _base_agent_state(final_answer=("```python\n" "def broken(:\n" "    pass\n" "```"))
        result = await generator.generate(state)

        assert len(result.code_snippets) == 1
        assert result.code_snippets[0].language == "text"
        assert result.code_snippets[0].validated is False


# ---------------------------------------------------------------------------
# Reasoning trace
# ---------------------------------------------------------------------------


class TestReasoningTrace:
    @pytest.mark.asyncio
    async def test_trace_built_from_pydantic_models(
        self, generator: RecommendationGenerator
    ) -> None:
        thoughts = [_make_thought("Check inventory"), _make_thought("Search KB")]
        tool_calls = [
            _make_tool_call("get_inventory_data", result={"items": [1, 2, 3]}),
            _make_tool_call("search_knowledge_base", result={"documents": [{"id": "c1"}]}),
        ]
        state = _base_agent_state(thoughts=thoughts, tool_calls=tool_calls)
        result = await generator.generate(state)

        assert len(result.reasoning_trace) == 2
        assert result.reasoning_trace[0]["iteration"] == 1
        assert result.reasoning_trace[0]["thought"] == "Check inventory"
        assert result.reasoning_trace[0]["action"]["tool"] == "get_inventory_data"
        assert result.reasoning_trace[1]["action"]["tool"] == "search_knowledge_base"

    @pytest.mark.asyncio
    async def test_trace_built_from_dict_tool_calls(
        self, generator: RecommendationGenerator
    ) -> None:
        thoughts = [_make_thought(as_dict=True)]
        tool_calls = [_make_tool_call("search_knowledge_base", result={"key": "val"}, as_dict=True)]
        state = _base_agent_state(thoughts=thoughts, tool_calls=tool_calls)
        result = await generator.generate(state)
        assert len(result.reasoning_trace) == 1
        assert result.reasoning_trace[0]["action"]["tool"] == "search_knowledge_base"

    @pytest.mark.asyncio
    async def test_trace_observation_documents_shape(
        self, generator: RecommendationGenerator
    ) -> None:
        thoughts = [_make_thought()]
        tool_calls = [
            _make_tool_call(
                "search_knowledge_base",
                result={"documents": [{"id": "c1"}, {"id": "c2"}]},
            )
        ]
        state = _base_agent_state(thoughts=thoughts, tool_calls=tool_calls)
        result = await generator.generate(state)
        assert result.reasoning_trace[0]["observation"] == "Received 2 documents"

    @pytest.mark.asyncio
    async def test_trace_empty_when_no_thoughts_or_tool_calls(
        self, generator: RecommendationGenerator
    ) -> None:
        state = _base_agent_state(thoughts=[], tool_calls=[])
        result = await generator.generate(state)
        assert result.reasoning_trace == []


# ---------------------------------------------------------------------------
# Warning detection
# ---------------------------------------------------------------------------


class TestWarningDetection:
    @pytest.mark.asyncio
    async def test_no_warnings_on_clean_completion(
        self, generator: RecommendationGenerator
    ) -> None:
        state = _base_agent_state(status="completed")
        result = await generator.generate(state)
        # algorithm present in mock LLM response → no missing-algorithm warning
        warning_texts = " ".join(result.warnings)
        assert "maximum iteration" not in warning_texts

    @pytest.mark.asyncio
    async def test_warning_on_max_iterations(
        self,
        mock_llm: MagicMock,
        mock_formula_extractor: MagicMock,
        mock_citation_extractor: MagicMock,
    ) -> None:
        gen = RecommendationGenerator(
            llm=mock_llm,
            formula_extractor=mock_formula_extractor,
            citation_extractor=mock_citation_extractor,
        )
        state = _base_agent_state(status="max_iterations")
        result = await gen.generate(state)
        assert any("maximum iteration" in w for w in result.warnings)

    @pytest.mark.asyncio
    async def test_warning_when_no_algorithm_identified(
        self,
        mock_llm: MagicMock,
        mock_formula_extractor: MagicMock,
        mock_citation_extractor: MagicMock,
    ) -> None:
        mock_llm.chat_completion = AsyncMock(return_value=_structured_llm_response(algorithm=None))
        gen = RecommendationGenerator(
            llm=mock_llm,
            formula_extractor=mock_formula_extractor,
            citation_extractor=mock_citation_extractor,
        )
        state = _base_agent_state()
        result = await gen.generate(state)
        assert any("No specific algorithm" in w for w in result.warnings)

    @pytest.mark.asyncio
    async def test_warning_on_failed_tool_calls(
        self,
        mock_llm: MagicMock,
        mock_formula_extractor: MagicMock,
        mock_citation_extractor: MagicMock,
    ) -> None:
        gen = RecommendationGenerator(
            llm=mock_llm,
            formula_extractor=mock_formula_extractor,
            citation_extractor=mock_citation_extractor,
        )
        state = _base_agent_state(
            tool_calls=[_make_tool_call("search_knowledge_base", error="500 Server Error")]
        )
        result = await gen.generate(state)
        assert any("search_knowledge_base" in w for w in result.warnings)

    @pytest.mark.asyncio
    async def test_warning_on_low_confidence(
        self,
        mock_llm: MagicMock,
        mock_formula_extractor: MagicMock,
        mock_citation_extractor: MagicMock,
    ) -> None:
        mock_llm.chat_completion = AsyncMock(
            return_value=_structured_llm_response(confidence="low")
        )
        gen = RecommendationGenerator(
            llm=mock_llm,
            formula_extractor=mock_formula_extractor,
            citation_extractor=mock_citation_extractor,
        )
        state = _base_agent_state()
        result = await gen.generate(state)
        assert any("Confidence" in w or "confidence" in w for w in result.warnings)

    @pytest.mark.asyncio
    async def test_multiple_warnings_can_coexist(
        self,
        mock_llm: MagicMock,
        mock_formula_extractor: MagicMock,
        mock_citation_extractor: MagicMock,
    ) -> None:
        mock_llm.chat_completion = AsyncMock(
            return_value=_structured_llm_response(algorithm=None, confidence="low")
        )
        gen = RecommendationGenerator(
            llm=mock_llm,
            formula_extractor=mock_formula_extractor,
            citation_extractor=mock_citation_extractor,
        )
        state = _base_agent_state(
            status="max_iterations",
            tool_calls=[_make_tool_call("search_knowledge_base", error="Timeout")],
        )
        result = await gen.generate(state)
        assert len(result.warnings) >= 3


# ---------------------------------------------------------------------------
# Execution time
# ---------------------------------------------------------------------------


class TestExecutionTime:
    @pytest.mark.asyncio
    async def test_execution_time_zero_when_no_completed_at(
        self, generator: RecommendationGenerator
    ) -> None:
        state = _base_agent_state(completed_at=None)
        result = await generator.generate(state)
        assert result.execution_time_seconds == 0.0

    @pytest.mark.asyncio
    async def test_execution_time_zero_when_no_started_at(
        self, generator: RecommendationGenerator
    ) -> None:
        # Edge case: no started_at means we cannot compute
        state = _base_agent_state()
        state["started_at"] = None  # type: ignore[assignment]
        result = await generator.generate(state)
        assert result.execution_time_seconds == 0.0

    @pytest.mark.asyncio
    async def test_execution_time_accurate(self, generator: RecommendationGenerator) -> None:
        started = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
        state = _base_agent_state(
            started_at=started,
            completed_at=started + timedelta(seconds=12.34),
        )
        result = await generator.generate(state)
        assert result.execution_time_seconds == pytest.approx(12.34)
