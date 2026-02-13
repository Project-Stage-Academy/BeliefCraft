"""LLM Service wrapper for AWS Bedrock (Claude) with retry logic."""

import json
from typing import Any

import boto3  # type: ignore[import-not-found]
import structlog
from app.config import get_settings
from app.core.exceptions import LLMServiceError
from langchain_aws import ChatBedrock  # type: ignore[import-not-found]
from langchain_core.messages import (  # type: ignore[import-not-found]
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from tenacity import (  # type: ignore[import-not-found]
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = structlog.get_logger()


class LLMService:
    """Wrapper for AWS Bedrock (Claude) with retry logic and unified response format."""

    def __init__(self) -> None:
        self.settings = get_settings()

        self.boto_client = boto3.client(
            "bedrock-runtime",
            region_name=self.settings.AWS_DEFAULT_REGION,
            aws_access_key_id=self.settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=self.settings.AWS_SECRET_ACCESS_KEY,
        )

        self.llm = ChatBedrock(
            client=self.boto_client,
            model_id=self.settings.BEDROCK_MODEL_ID,
            model_kwargs={
                "temperature": self.settings.BEDROCK_TEMPERATURE,
                "max_tokens": self.settings.BEDROCK_MAX_TOKENS,
            },
        )

    def _convert_messages_to_langchain(self, messages: list[dict[str, Any]]) -> list[BaseMessage]:
        """Convert dictionary messages to LangChain Message objects."""
        lc_messages: list[BaseMessage] = []
        for msg in messages:
            role = msg.get("role")
            content = msg.get("content") or ""

            if role == "system":
                lc_messages.append(SystemMessage(content=content))
            elif role == "user":
                lc_messages.append(HumanMessage(content=content))
            elif role == "assistant":
                tool_calls = msg.get("tool_calls") or []
                lc_messages.append(AIMessage(content=content, tool_calls=tool_calls))
            elif role == "tool":
                lc_messages.append(
                    ToolMessage(
                        tool_call_id=msg["tool_call_id"],
                        content=content,
                        name=msg.get("name", "tool"),
                    )
                )
        return lc_messages

    @retry(  # type: ignore[misc]
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(LLMServiceError),
        reraise=True,
    )
    async def chat_completion(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] = "auto",
    ) -> dict[str, Any]:
        """Call AWS Bedrock Claude model.

        Args:
            messages: Chat history as list of dicts.
            tools: Available tools in OpenAI-compatible JSON schema.
            tool_choice: Tool selection strategy.

        Returns:
            Unified dictionary with message, tool_calls, finish_reason, and tokens.
        """
        try:
            logger.info(
                "llm_request",
                model=self.llm.model_id,
                message_count=len(messages),
                has_tools=tools is not None,
            )

            lc_messages = self._convert_messages_to_langchain(messages)

            chain = self.llm
            if tools:
                chain = self.llm.bind_tools(tools)

            response = await chain.ainvoke(lc_messages)

            usage = response.response_metadata.get("usage", {})
            prompt_tokens = usage.get("input_tokens", 0)
            completion_tokens = usage.get("output_tokens", 0)

            stop_reason = response.response_metadata.get("stop_reason")
            finish_reason = "tool_calls" if stop_reason == "tool_use" else "stop"

            if response.tool_calls and finish_reason != "tool_calls":
                finish_reason = "tool_calls"

            # Extract text content — response.content may be a string or a
            # list of content blocks (e.g. [{"type": "text", "text": "..."}]).
            if isinstance(response.content, str):
                message_content = response.content
            elif isinstance(response.content, list):
                message_content = "".join(
                    block.get("text", "")
                    for block in response.content
                    if isinstance(block, dict) and block.get("type") == "text"
                )
            else:
                message_content = ""

            result: dict[str, Any] = {
                "message": {
                    "role": "assistant",
                    "content": message_content,
                },
                "tool_calls": [],
                "finish_reason": finish_reason,
                "tokens": {
                    "prompt": prompt_tokens,
                    "completion": completion_tokens,
                    "total": prompt_tokens + completion_tokens,
                },
            }

            if response.tool_calls:
                result["tool_calls"] = [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {
                            "name": tc["name"],
                            "arguments": (
                                json.dumps(tc["args"])
                                if isinstance(tc["args"], dict)
                                else str(tc["args"])
                            ),
                        },
                    }
                    for tc in response.tool_calls
                ]

            logger.info(
                "llm_response",
                finish_reason=finish_reason,
                tool_calls_count=len(result["tool_calls"]),
                tokens=result["tokens"]["total"],
            )

            return result

        except LLMServiceError:
            raise
        except Exception as e:
            logger.error(
                "llm_error",
                error_type=type(e).__name__,
                error_message=str(e),
            )
            raise LLMServiceError(f"Bedrock LLM call failed: {e}") from e

    async def extract_thought(self, messages: list[dict[str, Any]]) -> str:
        """Extract reasoning from LLM without tools (pure text generation)."""
        response = await self.chat_completion(messages=messages, tools=None)
        return str(response["message"]["content"])
