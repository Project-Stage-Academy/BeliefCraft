"""Base agent class for LangGraph-based agents."""

import json
from abc import ABC, abstractmethod
from typing import Any, cast

from app.services.llm_service import LLMService
from app.tools.registry import ToolRegistry
from common.logging import get_logger
from langgraph.graph.state import CompiledStateGraph

logger = get_logger(__name__)


class BaseAgent(ABC):
    """Abstract base class for LangGraph-based agents.

    Provides common initialization, tool execution, and LLM communication.
    Subclasses must implement _build_graph() to define their specific architecture.
    """

    def __init__(self, model_id: str, system_prompt: str, tool_registry: ToolRegistry) -> None:
        """Initialize the agent with LLM configuration and system prompt.

        Args:
            model_id: The model identifier to use for LLM service.
            system_prompt: The system prompt that guides the agent's behavior.
            tool_registry: Pre-configured ToolRegistry with agent-specific tools.
        """
        self.llm: LLMService = LLMService(model_id=model_id)
        self.system_prompt = system_prompt
        self.tool_registry = tool_registry
        self.graph = self._build_graph()
        logger.info(
            "base_agent_initialized",
            agent_class=self.__class__.__name__,
            model_id=model_id,
            tools_count=len(tool_registry.tools),
        )

    @abstractmethod
    def _build_graph(self) -> CompiledStateGraph[Any, Any, Any, Any]:
        """Build the state machine graph for this agent.

        Subclasses must implement this method to define the specific
        agent architecture (nodes, edges, conditional routing).

        Returns:
            A compiled CompiledStateGraph ready for execution.
        """
        pass

    @abstractmethod
    async def run(self, *args: Any, **kwargs: Any) -> Any:
        """Execute the agent with the given input.

        Subclasses must implement this method to define how the agent
        processes input and returns output. The signature can vary per
        agent type (e.g., ReActAgent takes user_query, EnvSubAgent may
        take different parameters).

        Args:
            *args: Positional arguments specific to the agent type.
            **kwargs: Keyword arguments specific to the agent type.
                      Common kwargs may include:
                      - max_iterations: Iteration limit for loops
                      - context: Additional context/metadata
                      - timeout: Execution timeout

        Returns:
            Final state/result of agent execution (type varies by agent).

        Raises:
            Exception: Implementation-specific exceptions for failures.
        """
        pass

    # ========== LLM Communication ==========

    async def _call_llm(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        """Make the LLM API call with messages and tool definitions.

        Args:
            messages: List of messages to send to the LLM.

        Returns:
            LLM response dictionary containing message, tool_calls, tokens, etc.
        """
        tools = self._get_tool_definitions()
        result = await self.llm.chat_completion(
            messages=messages,
            tools=tools if tools else None,
            tool_choice="auto",
        )
        return result

    # ========== Tool Execution & Management ==========

    async def _execute_all_tools(
        self, pending_calls: list[dict[str, Any]], request_id: str
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Execute all pending tool calls and collect results.

        Args:
            pending_calls: List of tool call dictionaries from the assistant message.
            request_id: Request ID for logging.

        Returns:
            Tuple of (new_messages, tool_results) containing tool response messages
            and structured tool result objects.
        """
        new_messages: list[dict[str, Any]] = []
        tool_results: list[dict[str, Any]] = []

        for tool_call in pending_calls:
            func_name = tool_call["function"]["name"]
            tool_call_id = tool_call["id"]
            func_args = self._parse_tool_arguments(tool_call["function"]["arguments"])
            tool_category = self._get_tool_category(func_name)

            logger.info(
                "executing_tool",
                request_id=request_id,
                tool=func_name,
                tool_call_id=tool_call_id,
            )

            result = await self._execute_tool(func_name, func_args)

            if result.get("status") == "error":
                error_msg = result.get("error", "Unknown tool error")
                logger.error(
                    "tool_execution_error",
                    request_id=request_id,
                    tool=func_name,
                    tool_call_id=tool_call_id,
                    error=error_msg,
                )
                tool_results.append(
                    {
                        "tool_name": func_name,
                        "category": tool_category,
                        "arguments": func_args,
                        "error": error_msg,
                    }
                )
                # Report error back to LLM so it can reason about it
                new_messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "name": func_name,
                        "content": json.dumps({"error": error_msg}),
                    }
                )
            else:
                tool_data = result.get("data", {})
                tool_meta = result.get("meta", {})
                tool_data, tool_meta = self._normalize_tool_success_payload(
                    tool_category, tool_data, tool_meta
                )
                logger.info(
                    "tool_execution_success",
                    request_id=request_id,
                    tool=func_name,
                    tool_call_id=tool_call_id,
                )
                tool_results.append(
                    {
                        "tool_name": func_name,
                        "category": tool_category,
                        "arguments": func_args,
                        "result": tool_data,
                        "trace_meta": tool_meta,
                    }
                )
                new_messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "name": func_name,
                        "content": json.dumps(tool_data),
                    }
                )

        return new_messages, tool_results

    async def _execute_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Execute a tool and handle success/error wrapping.

        Args:
            tool_name: Name of the tool to invoke.
            arguments: Parsed arguments to pass to the tool.

        Returns:
            ``{"status": "success", "data": ...}`` on success, or
            ``{"status": "error", "error": ..., "message": ...}`` on failure.
            Never raises — all exceptions are captured and returned as error dicts.
        """
        try:
            result = await self.tool_registry.execute_tool(tool_name, arguments)

            if result.success:
                return {"status": "success", "data": cast(dict[str, Any], result.data)}

            error_msg = result.error or "Tool reported failure without a message"
            logger.warning("tool_execution_failed", tool=tool_name, error=error_msg)
            return {
                "status": "error",
                "error": error_msg,
                "message": f"Tool execution failed: {error_msg}",
            }
        except Exception as e:
            logger.error("tool_execution_unexpected_error", tool=tool_name, error=str(e))
            return {
                "status": "error",
                "error": str(e),
                "message": f"Unexpected tool error: {str(e)}",
            }

    def _get_tool_definitions(self) -> list[dict[str, Any]]:
        """Get OpenAI function calling schemas for all tools."""
        return self.tool_registry.get_openai_functions()

    # ========== Tool Utilities ==========

    @staticmethod
    def _normalize_tool_success_payload(
        tool_category: str | None,
        tool_data: Any,
        tool_meta: Any,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Normalize tool payloads before storing them in agent state."""
        if (
            tool_category == "environment"
            and isinstance(tool_data, dict)
            and "data" in tool_data
            and isinstance(tool_data.get("meta"), dict)
        ):
            tool_meta = tool_data["meta"]
            tool_data = tool_data["data"]

        if not isinstance(tool_meta, dict):
            tool_meta = {}

        if not isinstance(tool_data, dict):
            tool_data = {"result": tool_data}

        return tool_data, tool_meta

    def _get_tool_category(self, tool_name: str) -> str | None:
        """Resolve category from the registered tool metadata when available."""
        try:
            return self.tool_registry.get_tool(tool_name).get_metadata().category
        except Exception:  # noqa: BLE001
            return None

    @staticmethod
    def _parse_tool_arguments(raw_args: str | dict[str, Any]) -> dict[str, Any]:
        """Parse tool arguments from string or dict with fallback."""
        if isinstance(raw_args, dict):
            return raw_args
        try:
            return json.loads(raw_args)  # type: ignore[no-any-return]
        except (json.JSONDecodeError, TypeError):
            return {"query": raw_args}
