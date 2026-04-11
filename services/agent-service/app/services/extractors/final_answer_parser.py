"""LLM-backed parsing of raw final answers into structured intermediate data."""

import json
import re
from typing import Any, Literal

from app.models.responses import Recommendation
from app.services.llm_service import LLMService
from common.logging import get_logger
from pydantic import BaseModel, ConfigDict, Field

logger = get_logger(__name__)

_PARSE_SYSTEM_PROMPT = "You are a data extraction assistant. Always return valid JSON."

_PARSE_USER_PROMPT = """\
## Agent Response
{final_answer}

## Objective
Extract structured information from the agent response and return a single JSON object.

## Extraction Rules
1. Use the top-level heading as task when present.
2. Summarize the analysis faithfully, but do not add facts that are not supported by the
   agent response.
3. Return [] unless the agent response contains an explicit recommendations section such as
   "Recommendations", "Next Steps", "Action Plan", or "Containment Steps".
4. Return null for confidence unless the agent response contains an explicit response-level
   confidence statement or confidence section.
5. Do not treat phrases about low-confidence sensors or observations as response confidence.
6. Return null for algorithm unless the agent response explicitly names a relevant algorithm
   section, title, or label.
7. Do not infer, add, or paraphrase recommendations, confidence, task names, or algorithms.

## Output Schema
{{
  "task": "Top-level task title or heading when present, otherwise null",
  "analysis": "Faithful summary of the situation analysis",
  "algorithm": "Algorithm name/number only when explicitly named, otherwise null",
  "recommendations": [
    {{
      "action": "Specific action to take from the explicit recommendations section",
      "priority": "high|medium|low",
      "rationale": "Why this action",
      "expected_outcome": "Expected result"
    }}
  ],
  "confidence": "high|medium|low if explicitly stated, otherwise null"
}}

## Output Requirements
- Return ONLY valid JSON.
- Do not wrap the JSON in markdown fences.
- Do not include any explanation or extra text.
"""

_JSON_FENCE_PATTERN = re.compile(r"```json\n(.*?)```", re.DOTALL)


class _RecommendationParseModel(BaseModel):
    model_config = ConfigDict(extra="ignore")

    action: str
    priority: Literal["high", "medium", "low"]
    rationale: str
    expected_outcome: str | None = None


class ParsedFinalAnswer(BaseModel):
    """Structured intermediate representation extracted from the raw final answer."""

    model_config = ConfigDict(extra="ignore")

    task: str | None = None
    analysis: str | None = None
    algorithm: str | None = None
    recommendations: list[_RecommendationParseModel] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low"] | None = None


class FinalAnswerParser:
    """Parse a raw final answer into a structured dictionary using the LLM."""

    def __init__(self, llm: LLMService) -> None:
        self.llm = llm

    async def parse(self, final_answer: str) -> tuple[dict[str, Any], dict[str, Any]]:
        """Parse the raw final answer into a structured dictionary.

        Returns:
            Tuple of (parsed_data, tokens).
        """
        messages = self._build_messages(final_answer)

        structured_data, tokens = await self._try_structured_parse(messages)
        if structured_data is not None:
            return structured_data, tokens

        json_data, tokens = await self._try_json_parse(messages)
        if json_data is not None:
            return json_data, tokens

        return self._fallback_parse(final_answer), self._empty_tokens()

    @staticmethod
    def _build_messages(final_answer: str) -> list[dict[str, Any]]:
        return [
            {"role": "system", "content": _PARSE_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": _PARSE_USER_PROMPT.format(final_answer=final_answer),
            },
        ]

    async def _try_structured_parse(
        self,
        messages: list[dict[str, Any]],
    ) -> tuple[dict[str, Any] | None, dict[str, Any]]:
        if not isinstance(self.llm, LLMService):
            return None, self._empty_tokens()

        try:
            result = await self.llm.structured_completion(
                messages=messages,
                schema=ParsedFinalAnswer,
            )
            structured_result = result["parsed"]
            tokens = result["tokens"]
        except Exception as exc:  # noqa: BLE001
            logger.warning("final_answer_structured_parsing_failed", error=str(exc))
            return None, self._empty_tokens()

        return self._normalize_structured_result(structured_result), tokens

    async def _try_json_parse(
        self, messages: list[dict[str, Any]]
    ) -> tuple[dict[str, Any] | None, dict[str, Any]]:
        try:
            response = await self.llm.chat_completion(messages=messages, tools=None)
            content = self._strip_json_fences(response["message"]["content"])
            parsed_content: dict[str, Any] = json.loads(content)
            tokens = response["tokens"]
        except Exception as exc:  # noqa: BLE001
            logger.warning("final_answer_parsing_failed", error=str(exc))
            return None, self._empty_tokens()

        return self._normalize_recommendations(parsed_content), tokens

    @staticmethod
    def _empty_tokens() -> dict[str, Any]:
        return {
            "prompt": 0,
            "completion": 0,
            "total": 0,
            "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 0,
        }

    @staticmethod
    def _normalize_structured_result(structured_result: Any) -> dict[str, Any]:
        if isinstance(structured_result, ParsedFinalAnswer):
            structured = structured_result.model_dump()
        elif isinstance(structured_result, dict):
            structured = structured_result
        else:
            structured = dict(structured_result)

        return FinalAnswerParser._normalize_recommendations(structured)

    @staticmethod
    def _normalize_recommendations(parsed_content: dict[str, Any]) -> dict[str, Any]:
        raw_recommendations = parsed_content.get("recommendations")
        if not isinstance(raw_recommendations, list):
            parsed_content["recommendations"] = []
            return parsed_content

        parsed_content["recommendations"] = [
            Recommendation(**recommendation) for recommendation in raw_recommendations
        ]
        return parsed_content

    @staticmethod
    def _strip_json_fences(content: str) -> str:
        json_match = _JSON_FENCE_PATTERN.search(content)
        if json_match:
            return json_match.group(1)
        return content

    @staticmethod
    def _fallback_parse(final_answer: str) -> dict[str, Any]:
        return {
            "task": "Analysis",
            "analysis": final_answer,
            "recommendations": [],
        }
