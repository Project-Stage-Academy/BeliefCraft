"""LLM Service wrapper for AWS Bedrock (Claude) with retry logic."""

import json
from typing import Any

import boto3
from app.config_load import settings
from app.core.exceptions import LLMServiceError
from botocore.config import Config
from common.logging import get_logger
from langchain_aws import ChatBedrock
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = get_logger(__name__)


class LLMService:
    """Wrapper for AWS Bedrock (Claude) with retry logic and unified response format."""

    def __init__(
        self, boto_client: Any = None, llm: Any = None, model_id: str | None = None
    ) -> None:
        """Initialize LLM service with optional dependency injection.

        Args:
            boto_client: Pre-configured boto3 Bedrock client. If None, creates default.
            llm: Pre-configured ChatBedrock instance. If None, creates default.
            model_id: Specific Bedrock model ID. If None, uses settings default.
        """
        self.model_id = model_id or settings.react_agent.model_id
        self.boto_client = boto_client or self._create_boto_client()
        self.llm = llm or self._create_llm()

    def _create_boto_client(self) -> Any:
        """Create and configure boto3 Bedrock client.

        Supports three authentication strategies (checked in order):
        1. Named AWS CLI profile (AWS_PROFILE setting)
        2. Explicit access key credentials (AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY)
        3. Default boto3 credential chain (~/.aws/credentials, env vars, IAM roles)

        Returns:
            Configured boto3 bedrock-runtime client.
        """
        region = settings.bedrock.region
        client_config = Config(
            connect_timeout=settings.bedrock.connect_timeout_seconds,
            read_timeout=settings.bedrock.read_timeout_seconds,
        )

        if settings.bedrock.aws_profile:
            logger.info("Using AWS profile '%s' for Bedrock client", settings.bedrock.aws_profile)
            session = boto3.Session(
                profile_name=settings.bedrock.aws_profile,
                region_name=region,
            )
            return session.client("bedrock-runtime", config=client_config)

        client_kwargs: dict[str, Any] = {
            "service_name": "bedrock-runtime",
            "region_name": region,
            "config": client_config,
        }

        if settings.bedrock.aws_access_key_id and settings.bedrock.aws_secret_access_key:
            client_kwargs["aws_access_key_id"] = settings.bedrock.aws_access_key_id
            client_kwargs["aws_secret_access_key"] = settings.bedrock.aws_secret_access_key
        else:
            logger.info("No explicit AWS credentials; using default boto3 credential chain")

        return boto3.client(**client_kwargs)

    def _create_bedrock_control_client(self) -> Any:
        """Create Bedrock control-plane client for model metadata lookups."""
        region = settings.bedrock.region
        client_config = Config(
            connect_timeout=settings.bedrock.connect_timeout_seconds,
            read_timeout=settings.bedrock.read_timeout_seconds,
        )

        if settings.bedrock.aws_profile:
            session = boto3.Session(
                profile_name=settings.bedrock.aws_profile,
                region_name=region,
            )
            return session.client("bedrock", config=client_config)

        client_kwargs: dict[str, Any] = {
            "service_name": "bedrock",
            "region_name": region,
            "config": client_config,
        }

        if settings.bedrock.aws_access_key_id and settings.bedrock.aws_secret_access_key:
            client_kwargs["aws_access_key_id"] = settings.bedrock.aws_access_key_id
            client_kwargs["aws_secret_access_key"] = settings.bedrock.aws_secret_access_key

        return boto3.client(**client_kwargs)

    def _resolve_inference_profile_base_model_id(self) -> str | None:
        """Resolve the foundation model behind a Bedrock inference profile ARN."""
        if not self.model_id.startswith("arn:") or "inference-profile" not in self.model_id:
            return None

        try:
            control_client = self._create_bedrock_control_client()
            response = control_client.get_inference_profile(
                inferenceProfileIdentifier=self.model_id
            )
        except Exception:
            logger.warning(
                "bedrock_inference_profile_lookup_failed",
                model_id=self.model_id,
                exc_info=True,
            )
            return None

        models = response.get("models", [])
        if not models:
            return None

        model_arn = models[0].get("modelArn")
        if not model_arn or "/" not in model_arn:
            return None

        return str(model_arn).split("/")[-1]

    def _create_llm(self) -> ChatBedrock:
        """Create and configure ChatBedrock LLM instance.

        Returns:
            Configured ChatBedrock instance.
        """
        llm_kwargs: dict[str, Any] = {
            "client": self.boto_client,
            "model": self.model_id,
            "model_kwargs": {
                "temperature": settings.bedrock.temperature,
                "max_tokens": settings.bedrock.max_tokens,
            },
        }

        if self.model_id.startswith("arn:"):
            llm_kwargs["provider"] = "anthropic"
            if base_model_id := self._resolve_inference_profile_base_model_id():
                llm_kwargs["base_model_id"] = base_model_id

        return ChatBedrock(**llm_kwargs)

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

    def _extract_text_from_blocks(self, blocks: list[Any]) -> str:
        """Extract text content from list of content blocks."""
        return "".join(
            block.get("text", "")
            for block in blocks
            if isinstance(block, dict) and block.get("type") == "text"
        )

    def _extract_message_content(self, response: AIMessage) -> str:
        """Extract message content from LLM response.

        Args:
            response: AIMessage from LLM.

        Returns:
            Extracted text content as string.
        """
        if isinstance(response.content, str):
            return response.content
        if isinstance(response.content, list):
            return self._extract_text_from_blocks(response.content)
        return ""

    @retry(
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

            usage_metadata = response.usage_metadata or {}
            prompt_tokens = usage_metadata.get("input_tokens", 0)
            completion_tokens = usage_metadata.get("output_tokens", 0)

            stop_reason = response.response_metadata.get("stop_reason")
            finish_reason = "tool_calls" if stop_reason == "tool_use" else "stop"

            if response.tool_calls and finish_reason != "tool_calls":
                finish_reason = "tool_calls"

            message_content = self._extract_message_content(response)

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
                exc_info=True,
            )
            raise LLMServiceError(f"Bedrock LLM call failed: {e}") from e

    async def extract_thought(self, messages: list[dict[str, Any]]) -> str:
        """Extract reasoning from LLM without tools (pure text generation)."""
        response = await self.chat_completion(messages=messages, tools=None)
        return str(response["message"]["content"])

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(LLMServiceError),
        reraise=True,
    )
    async def structured_completion(
        self,
        messages: list[dict[str, Any]],
        schema: Any,
    ) -> Any:
        """
        Invoke model with native structured output enforcement.

        Args:
            messages: Chat history as list of dicts.
            schema: Pydantic model class or JSON schema dict for structured output.

        Returns:
            Parsed structured result produced by LangChain.
        """
        try:
            logger.info(
                "llm_structured_request",
                model=self.llm.model_id,
                message_count=len(messages),
            )

            lc_messages = self._convert_messages_to_langchain(messages)
            chain = self.llm.with_structured_output(schema)
            result = await chain.ainvoke(lc_messages)

            logger.info("llm_structured_response")
            return result

        except LLMServiceError:
            raise
        except Exception as e:
            logger.error(
                "llm_structured_error",
                error_type=type(e).__name__,
                error_message=str(e),
                exc_info=True,
            )
            raise LLMServiceError(f"Bedrock structured LLM call failed: {e}") from e
