"""Unit tests for LLMService with mocked ChatBedrock responses."""

from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage  # type: ignore[import-not-found]

from app.core.exceptions import LLMServiceError
from app.services.llm_service import LLMService


@pytest.fixture()
def mock_settings() -> MagicMock:
    settings = MagicMock()
    settings.AWS_DEFAULT_REGION = "us-east-1"
    settings.AWS_ACCESS_KEY_ID = "test-key"
    settings.AWS_SECRET_ACCESS_KEY = "test-secret"
    settings.BEDROCK_MODEL_ID = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
    settings.BEDROCK_TEMPERATURE = 0.0
    settings.BEDROCK_MAX_TOKENS = 4000
    return settings


@pytest.fixture()
def llm_service(mock_settings: MagicMock) -> Generator[LLMService, None, None]:
    with (
        patch("app.services.llm_service.get_settings", return_value=mock_settings),
        patch("app.services.llm_service.boto3") as mock_boto3,
        patch("app.services.llm_service.ChatBedrock") as mock_chat_bedrock,
    ):
        mock_boto3.client.return_value = MagicMock()
        mock_llm = MagicMock()
        mock_llm.model_id = mock_settings.BEDROCK_MODEL_ID
        mock_chat_bedrock.return_value = mock_llm
        service = LLMService()
        yield service


class TestMessageConversion:
    def test_system_message(self, llm_service: LLMService) -> None:
        messages = [{"role": "system", "content": "You are a helpful assistant."}]
        result = llm_service._convert_messages_to_langchain(messages)
        assert len(result) == 1
        assert isinstance(result[0], SystemMessage)
        assert result[0].content == "You are a helpful assistant."

    def test_user_message(self, llm_service: LLMService) -> None:
        messages = [{"role": "user", "content": "Hello"}]
        result = llm_service._convert_messages_to_langchain(messages)
        assert len(result) == 1
        assert isinstance(result[0], HumanMessage)
        assert result[0].content == "Hello"

    def test_assistant_message(self, llm_service: LLMService) -> None:
        messages = [{"role": "assistant", "content": "Hi there"}]
        result = llm_service._convert_messages_to_langchain(messages)
        assert len(result) == 1
        assert isinstance(result[0], AIMessage)
        assert result[0].content == "Hi there"

    def test_assistant_message_with_tool_calls(self, llm_service: LLMService) -> None:
        tool_calls = [{"id": "tc_1", "name": "search", "args": {"query": "test"}}]
        messages = [{"role": "assistant", "content": "", "tool_calls": tool_calls}]
        result = llm_service._convert_messages_to_langchain(messages)
        assert len(result) == 1
        assert isinstance(result[0], AIMessage)
        assert len(result[0].tool_calls) == 1
        assert result[0].tool_calls[0]["id"] == "tc_1"
        assert result[0].tool_calls[0]["name"] == "search"
        assert result[0].tool_calls[0]["args"] == {"query": "test"}

    def test_tool_message(self, llm_service: LLMService) -> None:
        messages = [
            {
                "role": "tool",
                "content": '{"result": "data"}',
                "tool_call_id": "tc_1",
                "name": "search",
            }
        ]
        result = llm_service._convert_messages_to_langchain(messages)
        assert len(result) == 1
        assert isinstance(result[0], ToolMessage)
        assert result[0].tool_call_id == "tc_1"
        assert result[0].name == "search"

    def test_tool_message_default_name(self, llm_service: LLMService) -> None:
        messages = [
            {"role": "tool", "content": "result", "tool_call_id": "tc_1"}
        ]
        result = llm_service._convert_messages_to_langchain(messages)
        assert result[0].name == "tool"

    def test_empty_content_defaults_to_empty_string(self, llm_service: LLMService) -> None:
        messages = [{"role": "user", "content": None}]
        result = llm_service._convert_messages_to_langchain(messages)
        assert result[0].content == ""

    def test_multi_message_conversation(self, llm_service: LLMService) -> None:
        messages = [
            {"role": "system", "content": "System prompt"},
            {"role": "user", "content": "Question"},
            {"role": "assistant", "content": "Answer"},
        ]
        result = llm_service._convert_messages_to_langchain(messages)
        assert len(result) == 3
        assert isinstance(result[0], SystemMessage)
        assert isinstance(result[1], HumanMessage)
        assert isinstance(result[2], AIMessage)

    def test_unknown_role_is_skipped(self, llm_service: LLMService) -> None:
        messages = [{"role": "unknown", "content": "ignored"}]
        result = llm_service._convert_messages_to_langchain(messages)
        assert len(result) == 0


class TestChatCompletion:
    @pytest.mark.asyncio()
    async def test_basic_text_response(self, llm_service: LLMService) -> None:
        mock_response = AIMessage(
            content="The stock level is 42 units.",
            response_metadata={
                "usage": {"input_tokens": 10, "output_tokens": 15},
                "stop_reason": "end_turn",
            },
        )
        llm_service.llm.ainvoke = AsyncMock(return_value=mock_response)

        result = await llm_service.chat_completion(
            messages=[{"role": "user", "content": "What is the stock level?"}]
        )

        assert result["message"]["role"] == "assistant"
        assert result["message"]["content"] == "The stock level is 42 units."
        assert result["finish_reason"] == "stop"
        assert result["tool_calls"] == []
        assert result["tokens"]["prompt"] == 10
        assert result["tokens"]["completion"] == 15
        assert result["tokens"]["total"] == 25

    @pytest.mark.asyncio()
    async def test_response_with_tool_calls(self, llm_service: LLMService) -> None:
        mock_response = AIMessage(
            content="",
            response_metadata={
                "usage": {"input_tokens": 20, "output_tokens": 30},
                "stop_reason": "tool_use",
            },
            tool_calls=[
                {
                    "id": "call_123",
                    "name": "search_inventory",
                    "args": {"warehouse_id": "WH-001", "item": "widget"},
                }
            ],
        )
        mock_chain = MagicMock()
        mock_chain.ainvoke = AsyncMock(return_value=mock_response)
        llm_service.llm.bind_tools = MagicMock(return_value=mock_chain)

        tools = [
            {
                "type": "function",
                "function": {
                    "name": "search_inventory",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]
        result = await llm_service.chat_completion(
            messages=[{"role": "user", "content": "Search warehouse"}],
            tools=tools,
        )

        assert result["finish_reason"] == "tool_calls"
        assert len(result["tool_calls"]) == 1
        tc = result["tool_calls"][0]
        assert tc["id"] == "call_123"
        assert tc["type"] == "function"
        assert tc["function"]["name"] == "search_inventory"
        assert '"warehouse_id": "WH-001"' in tc["function"]["arguments"]
        assert result["tokens"]["total"] == 50

    @pytest.mark.asyncio()
    async def test_tool_calls_detected_without_stop_reason(self, llm_service: LLMService) -> None:
        """finish_reason should be 'tool_calls' even if stop_reason is not 'tool_use'."""
        mock_response = AIMessage(
            content="",
            response_metadata={
                "usage": {"input_tokens": 5, "output_tokens": 10},
                "stop_reason": "end_turn",
            },
            tool_calls=[
                {"id": "call_456", "name": "lookup", "args": {"id": "1"}}
            ],
        )
        mock_chain = MagicMock()
        mock_chain.ainvoke = AsyncMock(return_value=mock_response)
        llm_service.llm.bind_tools = MagicMock(return_value=mock_chain)

        result = await llm_service.chat_completion(
            messages=[{"role": "user", "content": "Lookup"}],
            tools=[{"type": "function", "function": {"name": "lookup"}}],
        )
        assert result["finish_reason"] == "tool_calls"

    @pytest.mark.asyncio()
    async def test_list_content_extracts_text_blocks(self, llm_service: LLMService) -> None:
        """When response.content is a list of content blocks, text is extracted."""
        mock_response = AIMessage(
            content=[{"type": "text", "text": "hello"}],
            response_metadata={
                "usage": {"input_tokens": 5, "output_tokens": 5},
                "stop_reason": "end_turn",
            },
        )
        llm_service.llm.ainvoke = AsyncMock(return_value=mock_response)

        result = await llm_service.chat_completion(
            messages=[{"role": "user", "content": "Hi"}]
        )
        assert result["message"]["content"] == "hello"

    @pytest.mark.asyncio()
    async def test_list_content_multiple_text_blocks(self, llm_service: LLMService) -> None:
        """Multiple text blocks in content list are concatenated."""
        mock_response = AIMessage(
            content=[
                {"type": "text", "text": "first "},
                {"type": "tool_use", "id": "tc_1", "name": "x", "input": {}},
                {"type": "text", "text": "second"},
            ],
            response_metadata={
                "usage": {"input_tokens": 5, "output_tokens": 5},
                "stop_reason": "end_turn",
            },
        )
        llm_service.llm.ainvoke = AsyncMock(return_value=mock_response)

        result = await llm_service.chat_completion(
            messages=[{"role": "user", "content": "Hi"}]
        )
        assert result["message"]["content"] == "first second"

    @pytest.mark.asyncio()
    async def test_missing_usage_metadata(self, llm_service: LLMService) -> None:
        """Token counts default to 0 when usage metadata is absent."""
        mock_response = AIMessage(
            content="Response",
            response_metadata={"stop_reason": "end_turn"},
        )
        llm_service.llm.ainvoke = AsyncMock(return_value=mock_response)

        result = await llm_service.chat_completion(
            messages=[{"role": "user", "content": "Hi"}]
        )
        assert result["tokens"]["prompt"] == 0
        assert result["tokens"]["completion"] == 0
        assert result["tokens"]["total"] == 0

    @pytest.mark.asyncio()
    async def test_exception_wraps_in_llm_service_exception(self, llm_service: LLMService) -> None:
        llm_service.llm.ainvoke = AsyncMock(
            side_effect=RuntimeError("Connection refused")
        )

        with pytest.raises(LLMServiceError, match="Bedrock LLM call failed"):
            await llm_service.chat_completion(
                messages=[{"role": "user", "content": "Hi"}]
            )

    @pytest.mark.asyncio()
    async def test_tools_are_bound_when_provided(self, llm_service: LLMService) -> None:
        mock_response = AIMessage(
            content="done",
            response_metadata={
                "usage": {"input_tokens": 1, "output_tokens": 1},
                "stop_reason": "end_turn",
            },
        )
        mock_chain = MagicMock()
        mock_chain.ainvoke = AsyncMock(return_value=mock_response)
        llm_service.llm.bind_tools = MagicMock(return_value=mock_chain)

        tools = [{"type": "function", "function": {"name": "test_tool"}}]
        await llm_service.chat_completion(
            messages=[{"role": "user", "content": "test"}], tools=tools
        )

        llm_service.llm.bind_tools.assert_called_once_with(tools)

    @pytest.mark.asyncio()
    async def test_no_tools_calls_llm_directly(self, llm_service: LLMService) -> None:
        mock_response = AIMessage(
            content="direct response",
            response_metadata={
                "usage": {"input_tokens": 1, "output_tokens": 1},
                "stop_reason": "end_turn",
            },
        )
        llm_service.llm.ainvoke = AsyncMock(return_value=mock_response)

        await llm_service.chat_completion(
            messages=[{"role": "user", "content": "test"}]
        )

        llm_service.llm.ainvoke.assert_called_once()


class TestExtractThought:
    @pytest.mark.asyncio()
    async def test_extract_thought_returns_content(self, llm_service: LLMService) -> None:
        mock_response = AIMessage(
            content="I should search the inventory database.",
            response_metadata={
                "usage": {"input_tokens": 5, "output_tokens": 10},
                "stop_reason": "end_turn",
            },
        )
        llm_service.llm.ainvoke = AsyncMock(return_value=mock_response)

        result = await llm_service.extract_thought(
            messages=[{"role": "user", "content": "Think about this."}]
        )
        assert result == "I should search the inventory database."


class TestLLMServiceInit:
    def test_uses_settings_values(self, mock_settings: MagicMock) -> None:
        with (
            patch("app.services.llm_service.get_settings", return_value=mock_settings),
            patch("app.services.llm_service.boto3") as mock_boto3,
            patch("app.services.llm_service.ChatBedrock") as mock_chat_bedrock,
        ):
            mock_boto3.client.return_value = MagicMock()
            mock_chat_bedrock.return_value = MagicMock()

            LLMService()

            mock_boto3.client.assert_called_once_with(
                "bedrock-runtime",
                region_name="us-east-1",
                aws_access_key_id="test-key",
                aws_secret_access_key="test-secret",
            )
            mock_chat_bedrock.assert_called_once_with(
                client=mock_boto3.client.return_value,
                model_id="us.anthropic.claude-sonnet-4-5-20250929-v1:0",
                model_kwargs={
                    "temperature": 0.0,
                    "max_tokens": 4000,
                },
            )
