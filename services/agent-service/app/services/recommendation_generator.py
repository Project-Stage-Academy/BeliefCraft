"""Main recommendation generator – assembles structured agent responses from raw AgentState."""

from datetime import UTC, datetime
from typing import Any, Literal

from app.models.agent_state import AgentState
from app.models.responses import (
    AgentRecommendationResponse,
    Citation,
    CodeSnippet,
    Formula,
    Recommendation,
)
from app.services.extractors.citation_extractor import CitationExtractor
from app.services.extractors.code_extractor import CodeExtractor
from app.services.extractors.final_answer_parser import FinalAnswerParser
from app.services.extractors.formula_extractor import FormulaExtractor
from app.services.extractors.tool_result_utils import (
    collect_result_documents,
    is_rag_tool_call,
    tool_call_field,
)
from app.services.llm_service import LLMService
from app.services.reasoning_trace_formatter import ReasoningTraceFormatter
from common.logging import get_logger

logger = get_logger(__name__)

_ResponseStatus = Literal["completed", "partial", "failed", "max_iterations"]


def _coerce_status(status: str) -> _ResponseStatus:
    """Map AgentState status to the narrower AgentRecommendationResponse status."""
    if status in {"completed", "partial", "failed", "max_iterations"}:
        return status  # type: ignore[return-value]
    return "partial"


class RecommendationGenerator:
    """
    Generate structured recommendations from agent state.

    Orchestrates formula/code/citation extraction, LLM-based answer parsing,
    reasoning trace assembly, and warning detection.
    """

    def __init__(
        self,
        llm: LLMService | None = None,
        formula_extractor: FormulaExtractor | None = None,
        citation_extractor: CitationExtractor | None = None,
        code_extractor: CodeExtractor | None = None,
        final_answer_parser: FinalAnswerParser | None = None,
        reasoning_trace_formatter: ReasoningTraceFormatter | None = None,
    ) -> None:
        resolved_llm = llm or LLMService()
        self.formula_extractor = formula_extractor or FormulaExtractor()
        self.citation_extractor = citation_extractor or CitationExtractor()
        self.code_extractor = code_extractor or CodeExtractor()
        self.final_answer_parser = final_answer_parser or FinalAnswerParser(resolved_llm)
        self.reasoning_trace_formatter = reasoning_trace_formatter or ReasoningTraceFormatter()

    async def generate(self, agent_state: AgentState) -> AgentRecommendationResponse:
        """Generate structured recommendation from agent's final state."""
        logger.info("generating_recommendation", request_id=agent_state["request_id"])

        final_answer = agent_state.get("final_answer") or ""

        if not final_answer:
            return self._generate_fallback_response(agent_state)

        structured, parsing_tokens = await self.final_answer_parser.parse(final_answer)
        task = structured.get("task") or "Analysis"
        analysis = structured.get("analysis") or final_answer
        algorithm = structured.get("algorithm")
        recommendations = structured.get("recommendations") or []
        confidence = structured.get("confidence")

        formulas = self._extract_formulas(agent_state, final_answer)
        code_snippets = self._extract_code_snippets(agent_state, final_answer)
        citations = self._extract_citations(agent_state)

        tools_used = [
            tool_call_field(tc, "tool_name")
            for tc in agent_state["tool_calls"]
            if tool_call_field(tc, "tool_name")
        ]

        reasoning_trace = self.reasoning_trace_formatter.format(agent_state)
        iterations = self._count_iterations(agent_state, reasoning_trace)
        warnings = self._detect_warnings(
            agent_state,
            algorithm=algorithm,
            confidence=confidence,
        )

        # Aggregate tokens including final answer parsing overhead
        total_tokens = agent_state["total_tokens"] + parsing_tokens.get("total", 0)
        cache_read = agent_state["cache_read_input_tokens"] + parsing_tokens.get(
            "cache_read_input_tokens", 0
        )
        cache_creation = agent_state["cache_creation_input_tokens"] + parsing_tokens.get(
            "cache_creation_input_tokens", 0
        )

        execution_time = self._calc_execution_time(agent_state)

        response = AgentRecommendationResponse(
            request_id=agent_state["request_id"],
            query=agent_state["user_query"],
            final_answer=final_answer,
            task=task,
            analysis=analysis,
            algorithm=algorithm,
            formulas=formulas,
            code_snippets=code_snippets,
            recommendations=recommendations,
            citations=citations,
            status=_coerce_status(agent_state["status"]),
            confidence=confidence,
            reasoning_trace=reasoning_trace,
            iterations=iterations,
            total_tokens=total_tokens,
            cache_read_input_tokens=cache_read,
            cache_creation_input_tokens=cache_creation,
            execution_time_seconds=execution_time,
            tools_used=list(set(tools_used)),
            warnings=warnings,
        )

        logger.info(
            "recommendation_generated",
            request_id=agent_state["request_id"],
            formulas_count=len(formulas),
            code_snippets_count=len(code_snippets),
            citations_count=len(citations),
        )
        return response

    def _extract_formulas(self, agent_state: AgentState, final_answer: str) -> list[Formula]:
        """Extract formulas from final answer text and RAG tool results."""
        formulas: list[Formula] = []

        formulas.extend(self.formula_extractor.extract_from_text(final_answer))

        for tool_call in agent_state["tool_calls"]:
            if not is_rag_tool_call(tool_call):
                continue
            result = tool_call_field(tool_call, "result")
            documents = collect_result_documents(result)
            if documents:
                formulas.extend(self.formula_extractor.extract_from_rag_chunks(documents))

        return formulas

    def _extract_citations(self, agent_state: AgentState) -> list[Citation]:
        """Extract citations from agent tool call history."""
        return self.citation_extractor.extract_from_tool_calls(agent_state["tool_calls"])

    def _extract_code_snippets(
        self,
        agent_state: AgentState,
        final_answer: str,
    ) -> list[CodeSnippet]:
        """
        Extract code snippets via dedicated CodeExtractor service.
        """
        return self.code_extractor.extract_from_answer_and_tool_calls(
            final_answer=final_answer,
            tool_calls=agent_state["tool_calls"],
        )

    def _detect_warnings(
        self,
        agent_state: AgentState,
        *,
        algorithm: str | None,
        confidence: Literal["high", "medium", "low"] | None,
    ) -> list[str]:
        """Detect potential issues and limitations."""
        warnings: list[str] = []

        if agent_state["status"] == "max_iterations":
            warnings.append(
                "Analysis incomplete: reached maximum iteration limit. "
                "Results may be partial. Consider refining your query."
            )

        if not algorithm:
            warnings.append(
                "No specific algorithm from the knowledge base was identified. "
                "Response is based on general analysis."
            )

        failed_tools = [
            tool_call_field(tc, "tool_name")
            for tc in agent_state["tool_calls"]
            if tool_call_field(tc, "error")
        ]
        if failed_tools:
            warnings.append(
                f"Some tools failed during execution: {', '.join(t for t in failed_tools if t)}. "
                "Results may be incomplete."
            )

        if confidence == "low":
            warnings.append(
                "Confidence in recommendations is low due to data uncertainty or ambiguity."
            )

        return warnings

    def _generate_fallback_response(self, agent_state: AgentState) -> AgentRecommendationResponse:
        """Generate a minimal response when the agent failed or produced no output."""
        error_message = agent_state.get("error") or "Unknown error"
        reasoning_trace = self.reasoning_trace_formatter.format(agent_state)
        iterations = self._count_iterations(agent_state, reasoning_trace)

        return AgentRecommendationResponse(
            request_id=agent_state["request_id"],
            query=agent_state["user_query"],
            final_answer=agent_state.get("final_answer"),
            task="Analysis Failed",
            analysis=f"Unable to complete analysis. Error: {error_message}",
            recommendations=[
                Recommendation(
                    action="Review error and retry query",
                    priority="high",
                    rationale="Agent encountered an error during execution",
                )
            ],
            status="failed",
            reasoning_trace=reasoning_trace,
            iterations=iterations,
            total_tokens=agent_state["total_tokens"],
            cache_read_input_tokens=agent_state["cache_read_input_tokens"],
            cache_creation_input_tokens=agent_state["cache_creation_input_tokens"],
            execution_time_seconds=0.0,
            tools_used=[],
            warnings=[error_message],
        )

    @staticmethod
    def _count_iterations(agent_state: AgentState, reasoning_trace: list[dict[str, Any]]) -> int:
        """Report iterations using the public reasoning trace when available."""
        if reasoning_trace:
            return len(reasoning_trace)
        return agent_state["iteration"]

    @staticmethod
    def _calc_execution_time(agent_state: AgentState) -> float:
        """
        Calculate execution duration in seconds.
        Includes the agent loop and the recommendation generation overhead.
        """
        started_at = agent_state.get("started_at")
        if started_at is not None:
            return (datetime.now(UTC) - started_at).total_seconds()
        return 0.0
