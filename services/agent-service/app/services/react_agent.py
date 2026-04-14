"""ReAct agent implementation using LangGraph state machine."""

import json
from datetime import UTC, datetime
from typing import Any, Literal, cast

from app.config_load import settings
from app.core.exceptions import AgentExecutionError
from app.models.agent_state import (
    AgentState,
    ThoughtStep,
    create_initial_state,
    merge_token_usage,
)
from app.prompts.system_prompts import (
    WAREHOUSE_ADVISOR_SYSTEM_PROMPT,
    format_react_prompt,
)
from app.services.base_agent import BaseAgent
from app.services.message_parser import MessageParser
from app.tools.registry import ToolRegistry
from common.logging import get_logger
from langchain_core.messages import AIMessage
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode

logger = get_logger(__name__)


class ReActAgent(BaseAgent):
    """ReAct loop implementation using LangGraph for AWS Bedrock/Claude."""

    def __init__(
        self,
        system_prompt: str | None = None,
        tool_registry: ToolRegistry | None = None,
    ) -> None:
        """Initialize ReAct agent with optional custom system prompt and registry.

        Args:
            system_prompt: Custom system prompt. If None, uses default
                          WAREHOUSE_ADVISOR_SYSTEM_PROMPT.
            tool_registry: Pre-configured registry with RAG+skill tools.
                          If None, creates empty registry (for testing).
        """
        if tool_registry is None:
            raise ValueError("A configured ToolRegistry must be explicitly injected.")

        resolved_prompt = system_prompt or WAREHOUSE_ADVISOR_SYSTEM_PROMPT
        super().__init__(
            model_id=settings.react_agent.model_id,
            system_prompt=resolved_prompt,
            tool_registry=tool_registry,
        )

    def _build_graph(self) -> CompiledStateGraph[Any, Any, Any, Any]:
        """Build the ReAct state machine with think/act/finalize nodes."""
        workflow = StateGraph(AgentState)

        workflow.add_node("think", self._think_node)
        workflow.add_node("act", self._act_node_wrapper)
        workflow.add_node("finalize", self._finalize_node)

        workflow.set_entry_point("think")
        workflow.add_conditional_edges(
            "think",
            self._should_continue,
            {
                "continue": "act",
                "finalize": "finalize",
                "max_iterations": "finalize",
            },
        )

        workflow.add_edge("act", "think")
        workflow.add_edge("finalize", END)

        return workflow.compile()

    async def _act_node_wrapper(self, state: AgentState) -> dict[str, Any]:
        """Wrapper for native ToolNode to extract token usage from tools."""
        tool_node = ToolNode(self.lc_tools)
        result: dict[str, Any] = await tool_node.ainvoke(state)

        # Extract token_usage from ToolMessage content (e.g. from sub-agent calls)
        token_usage_deltas: dict[str, dict[str, int]] = {}
        for message in result.get("messages", []):
            if message.type == "tool":
                try:
                    data = json.loads(message.content)
                    if isinstance(data["data"], dict) and "token_usage" in data["data"]:
                        token_usage_deltas = merge_token_usage(
                            token_usage_deltas, data["data"]["token_usage"]
                        )
                        # Remove token_usage from the content so LLM doesn't see it
                        del data["data"]["token_usage"]
                        message.content = json.dumps(data)
                except (json.JSONDecodeError, TypeError):
                    continue

        if token_usage_deltas:
            result["token_usage"] = token_usage_deltas
        return result

    async def _think_node(self, state: AgentState) -> dict[str, Any]:
        """Reasoning step: Claude analyzes the situation and decides next action.

        Orchestrates the thinking process by building messages, calling the LLM,
        and parsing the response into state updates.
        """
        logger.info(
            "react_think",
            request_id=state["request_id"],
            iteration=state["iteration"],
        )

        # Early exit if max iterations already reached
        # (prevents unnecessary LLM calls when limit was just incremented)
        if state["iteration"] >= state["max_iterations"]:
            logger.warning(
                "max_iterations_check_in_think",
                request_id=state["request_id"],
                iteration=state["iteration"],
                max_iterations=state["max_iterations"],
            )
            return {"status": "max_iterations"}

        try:
            messages = self._build_llm_messages(state)
            cache = self._build_llm_cache_flags(messages, state)
            response = await self._call_llm(messages, cache)

            message_content = response["message"]["content"]
            tool_calls = response.get("tool_calls", [])

            # Format tool calls natively for LangChain compatibility
            ai_message = AIMessage(
                content=message_content,
                tool_calls=(
                    [
                        {
                            "name": tc["function"]["name"],
                            "args": json.loads(tc["function"]["arguments"]),
                            "id": tc["id"],
                        }
                        for tc in tool_calls
                    ]
                    if tool_calls
                    else []
                ),
            )

            next_action = "tool_use" if tool_calls else "answer"
            thought = ThoughtStep(
                thought=message_content,
                next_action=next_action,
            )

            updates: dict[str, Any] = {
                "messages": [ai_message],
                "thoughts": state["thoughts"] + [thought],
                "token_usage": {response["model_id"]: response["tokens"]},
                "iteration": state["iteration"] + 1,
            }

            # Detect final answer: LLM stopped without requesting tools
            if response["finish_reason"] == "stop" and not tool_calls:
                if "FINAL ANSWER:" in message_content:
                    updates["final_answer"] = message_content.split("FINAL ANSWER:", 1)[1].strip()
                else:
                    # Bare stop without tools treated as implicit final answer
                    updates["final_answer"] = message_content
                updates["status"] = "completed"

            logger.info(
                "react_think_complete",
                request_id=state["request_id"],
                iteration=state["iteration"],
                has_tool_calls=bool(tool_calls),
                has_final_answer="final_answer" in updates,
                tokens_used=response["tokens"]["total"],
            )

            return updates

        except Exception as e:
            logger.error(
                "react_think_error",
                request_id=state["request_id"],
                iteration=state["iteration"],
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True,
            )
            return {
                "status": "failed",
                "error": str(e),
            }

    def _build_llm_messages(self, state: AgentState) -> list[dict[str, Any]]:
        """Build the message list for LLM input.

        The formatted ReAct prompt encodes iteration info, user query, and
        XML history reconstructed from the stored assistant/tool messages.
        Raw conversation messages are NOT appended separately because the
        formatter already preserves exact assistant-turn boundaries there.

        Args:
            state: Current agent state.

        Returns:
            List of messages for LLM consumption.
        """
        messages = [{"role": "user", "content": message} for message in format_react_prompt(state)]
        return [
            {"role": "system", "content": self.system_prompt},
            *messages,
        ]

    def _build_llm_cache_flags(
        self, messages: list[dict[str, Any]], state: AgentState
    ) -> list[bool]:
        """Build the cache flags for LLM input."""
        cache = [False] * len(messages)
        # put checkpoint before last message, because
        # last one contains iteration number which always changes
        cache[-2] = True
        if state["iteration"] == state["max_iterations"] - 1:
            # don't cache message added at last iteration, because it will never be read again
            cache[-2] = False
        return cache

    def _should_continue(
        self, state: AgentState
    ) -> Literal["continue", "finalize", "max_iterations"]:
        """Route decision after the think node.

        Pure routing function — does not mutate state.
        """
        if state["status"] in ("failed", "completed", "max_iterations"):
            return "finalize"

        if state["final_answer"] is not None:
            return "finalize"

        return "continue"

    def _finalize_node(self, state: AgentState) -> dict[str, Any]:
        """Prepare the final response and set completion metadata."""
        logger.info(
            "react_finalize",
            request_id=state["request_id"],
            status=state["status"],
            iteration=state["iteration"],
        )

        updates: dict[str, Any] = {
            "completed_at": datetime.now(UTC),
        }

        if state["iteration"] >= state["max_iterations"] and not state["final_answer"]:
            updates["status"] = "max_iterations"
            updates["final_answer"] = (
                "Unable to complete analysis within iteration limit. "
                "Please refine your query or provide more specific context."
            )
        elif state["status"] == "running":
            updates["status"] = "completed"

        return updates

    async def run(
        self,
        user_query: str,
        context: dict[str, Any] | None = None,
        max_iterations: int = 10,
    ) -> AgentState:
        """Run the ReAct loop for a user query.

        Args:
            user_query: The user's question or command.
            context: Optional metadata (e.g. warehouse_id).
            max_iterations: Safety limit on think/act cycles.

        Returns:
            Final AgentState with answer, reasoning trace, and metadata.

        Raises:
            AgentExecutionError: If the graph fails unexpectedly.
        """
        logger.info(
            "react_agent_start",
            query=user_query[:200],
            max_iterations=max_iterations,
            has_context=context is not None,
        )

        initial_state = create_initial_state(
            user_query=user_query,
            context=context,
            max_iterations=max_iterations,
        )

        try:
            final_state = cast(AgentState, await self.graph.ainvoke(initial_state))
        except Exception as e:
            logger.error(
                "react_agent_error",
                request_id=initial_state["request_id"],
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True,
            )
            raise AgentExecutionError(f"ReAct agent execution failed: {e}") from e

        total_tokens = sum(
            counts.get("total", 0) for counts in final_state.get("token_usage", {}).values()
        )
        cache_read_tokens = sum(
            counts.get("cache_read_input_tokens", 0)
            for counts in final_state.get("token_usage", {}).values()
        )
        cache_creation_tokens = sum(
            counts.get("cache_creation_input_tokens", 0)
            for counts in final_state.get("token_usage", {}).values()
        )

        logger.info(
            "react_agent_complete",
            request_id=final_state["request_id"],
            status=final_state["status"],
            iterations=final_state["iteration"],
            tokens=total_tokens,
            cache_read_input_tokens=cache_read_tokens,
            cache_creation_input_tokens=cache_creation_tokens,
            thought_count=len(final_state["thoughts"]),
            tool_call_count=self._count_tool_executions(final_state.get("messages", [])),
        )

        return final_state
