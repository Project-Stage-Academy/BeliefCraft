"""
Main recommendation generator – assembles structured agent responses from raw AgentState.
"""

import json
import re
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
from app.services.extractors.formula_extractor import FormulaExtractor
from app.services.llm_service import LLMService
from common.logging import get_logger

logger = get_logger(__name__)

_ResponseStatus = Literal["completed", "partial", "failed", "max_iterations"]


def _coerce_status(status: str) -> _ResponseStatus:
    """Map AgentState status to the narrower AgentRecommendationResponse status."""
    if status in {"completed", "partial", "failed", "max_iterations"}:
        return status  # type: ignore[return-value]
    # 'running' or any unexpected value treated as partial
    return "partial"


_RAG_TOOL_NAMES = {"search_knowledge_base", "expand_graph_by_ids", "get_entity_by_number"}

_PARSE_SYSTEM_PROMPT = "You are a data extraction assistant. Always return valid JSON."

_PARSE_USER_PROMPT = """\
Extract structured information from the following agent response.

Agent response:
{final_answer}

Extract and return JSON with these fields:
{{
  "task": "High-level task (e.g., 'Inventory Replenishment', 'Risk Assessment')",
  "analysis": "Summary of the situation analysis",
  "algorithm": "Algorithm name/number if mentioned (e.g., 'Algorithm 3.2 - (s,S) Policy')",
  "recommendations": [
    {{
      "action": "Specific action to take",
      "priority": "high|medium|low",
      "rationale": "Why this action",
      "expected_outcome": "Expected result"
    }}
  ],
  "confidence": "high|medium|low"
}}

Return ONLY valid JSON, no other text.
"""


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
    ) -> None:
        self.llm = llm or LLMService()
        self.formula_extractor = formula_extractor or FormulaExtractor()
        self.citation_extractor = citation_extractor or CitationExtractor()
        self.code_extractor = code_extractor or CodeExtractor()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def generate(self, agent_state: AgentState) -> AgentRecommendationResponse:
        """Generate structured recommendation from agent's final state."""
        logger.info("generating_recommendation", request_id=agent_state["request_id"])

        final_answer = agent_state.get("final_answer") or ""

        if not final_answer:
            return self._generate_fallback_response(agent_state)

        # Parse final answer into structured components via LLM
        structured = await self._parse_final_answer(final_answer)

        formulas = self._extract_formulas(agent_state, final_answer)
        code_snippets = self._extract_code_snippets(agent_state, final_answer)
        citations = self._extract_citations(agent_state)

        tools_used = [
            self._field(tc, "tool_name")
            for tc in agent_state["tool_calls"]
            if self._field(tc, "tool_name")
        ]

        reasoning_trace = self._build_reasoning_trace(agent_state)
        warnings = self._detect_warnings(agent_state, structured)
        execution_time = self._calc_execution_time(agent_state)

        response = AgentRecommendationResponse(
            request_id=agent_state["request_id"],
            query=agent_state["user_query"],
            task=structured.get("task") or "Analysis",
            analysis=structured.get("analysis") or final_answer,
            algorithm=structured.get("algorithm"),
            formulas=formulas,
            code_snippets=code_snippets,
            recommendations=structured.get("recommendations")
            or [
                Recommendation(
                    action="Review agent output manually",
                    priority="medium",
                    rationale="Could not extract structured recommendations",
                )
            ],
            citations=citations,
            status=_coerce_status(agent_state["status"]),
            confidence=structured.get("confidence"),
            reasoning_trace=reasoning_trace,
            iterations=agent_state["iteration"],
            total_tokens=agent_state["total_tokens"],
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

    # ------------------------------------------------------------------
    # LLM-based answer parsing
    # ------------------------------------------------------------------

    async def _parse_final_answer(self, final_answer: str) -> dict[str, Any]:
        """Use LLM to parse the final answer into a structured dict."""
        messages = [
            {"role": "system", "content": _PARSE_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": _PARSE_USER_PROMPT.format(final_answer=final_answer),
            },
        ]

        try:
            response = await self.llm.chat_completion(messages=messages, tools=None)
            content: str = response["message"]["content"]

            # Strip optional markdown fences
            json_match = re.search(r"```json\n(.*?)```", content, re.DOTALL)
            if json_match:
                content = json_match.group(1)

            structured: dict[str, Any] = json.loads(content)

            # Convert recommendation dicts to Pydantic models
            if "recommendations" in structured and isinstance(structured["recommendations"], list):
                structured["recommendations"] = [
                    Recommendation(**rec) for rec in structured["recommendations"]
                ]

            return structured

        except Exception as exc:  # noqa: BLE001
            logger.warning("final_answer_parsing_failed", error=str(exc))
            return {
                "task": "Analysis",
                "analysis": final_answer,
                "recommendations": [
                    Recommendation(
                        action="Review agent output manually",
                        priority="medium",
                        rationale="Automated parsing failed",
                    )
                ],
            }

    # ------------------------------------------------------------------
    # Extraction helpers
    # ------------------------------------------------------------------

    def _extract_formulas(self, agent_state: AgentState, final_answer: str) -> list[Formula]:
        """Extract formulas from final answer text and RAG tool results."""
        formulas: list[Formula] = []

        formulas.extend(self.formula_extractor.extract_from_text(final_answer))

        for tool_call in agent_state["tool_calls"]:
            if self._field(tool_call, "tool_name") not in _RAG_TOOL_NAMES:
                continue
            result = self._field(tool_call, "result") or {}
            if isinstance(result, dict) and "documents" in result:
                formulas.extend(self.formula_extractor.extract_from_rag_chunks(result["documents"]))

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

    # ------------------------------------------------------------------
    # Reasoning trace
    # ------------------------------------------------------------------

    def _build_reasoning_trace(self, agent_state: AgentState) -> list[dict[str, Any]]:
        """Build a concise reasoning trace from thoughts + tool calls."""
        trace: list[dict[str, Any]] = []

        for i, (thought, tool_call) in enumerate(
            zip(agent_state["thoughts"], agent_state["tool_calls"], strict=False)
        ):
            thought_text = thought.thought if hasattr(thought, "thought") else str(thought)

            step: dict[str, Any] = {
                "iteration": i + 1,
                "thought": thought_text,
                "action": {
                    "tool": self._field(tool_call, "tool_name"),
                    "arguments": self._field(tool_call, "arguments"),
                },
            }

            result = self._field(tool_call, "result")
            if result:
                if isinstance(result, dict) and "documents" in result:
                    step["observation"] = f"Received {len(result['documents'])} documents"
                elif isinstance(result, dict):
                    step["observation"] = f"Received {len(result)} data points"
                else:
                    step["observation"] = "Success"

            trace.append(step)

        return trace

    # ------------------------------------------------------------------
    # Warning detection
    # ------------------------------------------------------------------

    def _detect_warnings(self, agent_state: AgentState, structured: dict[str, Any]) -> list[str]:
        """Detect potential issues and limitations."""
        warnings: list[str] = []

        if agent_state["status"] == "max_iterations":
            warnings.append(
                "Analysis incomplete: reached maximum iteration limit. "
                "Results may be partial. Consider refining your query."
            )

        if not structured.get("algorithm"):
            warnings.append(
                "No specific algorithm from the knowledge base was identified. "
                "Recommendations are based on general analysis."
            )

        failed_tools = [
            self._field(tc, "tool_name")
            for tc in agent_state["tool_calls"]
            if self._field(tc, "error")
        ]
        if failed_tools:
            warnings.append(
                f"Some tools failed during execution: {', '.join(t for t in failed_tools if t)}. "
                "Results may be incomplete."
            )

        if structured.get("confidence") == "low":
            warnings.append(
                "Confidence in recommendations is low due to data uncertainty or ambiguity."
            )

        return warnings

    # ------------------------------------------------------------------
    # Fallback response
    # ------------------------------------------------------------------

    def _generate_fallback_response(self, agent_state: AgentState) -> AgentRecommendationResponse:
        """Generate a minimal response when the agent failed or produced no output."""
        error_message = agent_state.get("error") or "Unknown error"

        return AgentRecommendationResponse(
            request_id=agent_state["request_id"],
            query=agent_state["user_query"],
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
            reasoning_trace=self._build_reasoning_trace(agent_state),
            iterations=agent_state["iteration"],
            total_tokens=agent_state["total_tokens"],
            execution_time_seconds=0.0,
            tools_used=[],
            warnings=[error_message],
        )

    # ------------------------------------------------------------------
    # Utility helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _field(obj: Any, name: str) -> Any:
        """Retrieve a field from a dict or Pydantic model."""
        if isinstance(obj, dict):
            return obj.get(name)
        return getattr(obj, name, None)

    @staticmethod
    def _calc_execution_time(agent_state: AgentState) -> float:
        """Calculate execution duration in seconds."""
        completed_at = agent_state.get("completed_at")
        started_at = agent_state.get("started_at")
        if completed_at is not None and started_at is not None:
            return (completed_at - started_at).total_seconds()
        return 0.0
