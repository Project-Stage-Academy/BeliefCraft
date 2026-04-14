"""Unit tests for LLM-backed final answer parsing."""

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from app.services.extractors.final_answer_parser import FinalAnswerParser
from app.services.llm_service import LLMService


class TestFinalAnswerParser:
    @pytest.mark.asyncio
    async def test_prompt_requires_explicit_sections_for_recommendations_and_confidence(
        self,
    ) -> None:
        llm = MagicMock()
        llm.chat_completion = AsyncMock(
            return_value={
                "message": {
                    "role": "assistant",
                    "content": json.dumps(
                        {
                            "task": None,
                            "analysis": "All good.",
                            "algorithm": None,
                            "recommendations": [],
                            "confidence": None,
                        }
                    ),
                },
                "tool_calls": [],
                "finish_reason": "stop",
                "model_id": "test-model",
                "tokens": {"prompt": 10, "completion": 10, "total": 20},
            }
        )

        parser = FinalAnswerParser(llm)

        result, token_usage = await parser.parse(
            "## Inventory Management\n\nObserved with low confidence sensors."
        )

        assert token_usage["test-model"]["total"] == 20
        messages = llm.chat_completion.await_args.kwargs["messages"]
        prompt = messages[1]["content"]
        assert "## Agent Response" in prompt
        assert "## Objective" in prompt
        assert "## Extraction Rules" in prompt
        assert "## Output Schema" in prompt
        assert "## Output Requirements" in prompt
        assert (
            "Return [] unless the agent response contains an explicit recommendations section"
            in prompt
        )
        assert "Do not treat phrases about low-confidence sensors or observations" in prompt
        assert "Use the top-level heading as task when present" in prompt

    @pytest.mark.asyncio
    async def test_uses_structured_completion_for_llmservice_subclass(self) -> None:
        class _StructuredOnlyLLM(LLMService):
            def __init__(self) -> None:
                pass

            async def structured_completion(
                self,
                messages: list[dict[str, Any]],
                schema: Any,
            ) -> dict[str, Any]:
                return {
                    "parsed": {
                        "task": "Inventory Management",
                        "analysis": "Structured analysis",
                        "algorithm": "Algorithm 2.2",
                        "recommendations": [
                            {
                                "action": "Apply policy",
                                "priority": "high",
                                "rationale": "Deterministic extraction",
                                "expected_outcome": "Lower risk",
                            }
                        ],
                        "confidence": "high",
                    },
                    "model_id": "sonnet",
                    "tokens": {"total": 150},
                }

            async def chat_completion(  # type: ignore[override]
                self,
                messages: list[dict[str, Any]],
                tools: list[dict[str, Any]] | None = None,
                tool_choice: str | dict[str, Any] = "auto",
            ) -> dict[str, Any]:
                raise AssertionError("chat_completion should not be used in this test")

        parser = FinalAnswerParser(_StructuredOnlyLLM())

        result, token_usage = await parser.parse(
            "## Inventory Management\n\n### Analysis\nStructured analysis"
        )

        assert token_usage["sonnet"]["total"] == 150
        assert result["analysis"] == "Structured analysis"
        assert result["confidence"] == "high"
        assert result["recommendations"][0].action == "Apply policy"

    @pytest.mark.asyncio
    async def test_strips_json_markdown_fences_from_chat_completion(self) -> None:
        llm = MagicMock()
        payload = json.dumps(
            {
                "task": "Inventory Management",
                "analysis": "All good.",
                "algorithm": None,
                "recommendations": [],
                "confidence": None,
            }
        )
        llm.chat_completion = AsyncMock(
            return_value={
                "message": {"role": "assistant", "content": f"```json\n{payload}\n```"},
                "tool_calls": [],
                "finish_reason": "stop",
                "model_id": "test-model",
                "tokens": {"prompt": 10, "completion": 10, "total": 20},
            }
        )

        parser = FinalAnswerParser(llm)
        result, token_usage = await parser.parse("## Inventory Management")

        assert token_usage["test-model"]["total"] == 20
        assert result["task"] == "Inventory Management"
        assert result["analysis"] == "All good."

    @pytest.mark.asyncio
    async def test_returns_fallback_payload_when_llm_output_is_invalid(self) -> None:
        llm = MagicMock()
        llm.chat_completion = AsyncMock(
            return_value={
                "message": {"role": "assistant", "content": "not valid json {{"},
                "tool_calls": [],
                "finish_reason": "stop",
                "model_id": "test-model",
                "tokens": {"prompt": 5, "completion": 5, "total": 10},
            }
        )

        parser = FinalAnswerParser(llm)
        result, token_usage = await parser.parse("Raw final answer")

        assert token_usage == {}  # Fallback doesn't return tokens
        assert result == {
            "task": "Analysis",
            "analysis": "Raw final answer",
            "recommendations": [],
        }
