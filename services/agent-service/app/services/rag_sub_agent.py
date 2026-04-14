import contextlib
import json
from datetime import UTC, datetime
from typing import Any, Literal, cast

from app.config_load import settings
from app.core.exceptions import AgentExecutionError
from app.models.agent_state import ThoughtStep
from app.models.rag_sub_agent_state import RAGSubAgentState, create_initial_state
from app.prompts.rag_sub_agent_system_prompts import (
    RAG_SUB_AGENT_SYSTEM_PROMPT,
    format_rag_react_prompt,
)
from app.services.base_agent import BaseAgent
from app.tools import BaseTool, ToolMetadata
from app.tools.registry import ToolRegistry
from common.logging import get_logger
from langchain_core.messages import AIMessage
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode

logger = get_logger(__name__)


class FinalAnswerTool(BaseTool):
    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="final_answer",
            description="Call this when you found all relevant documents",
            parameters={
                "type": "object",
                "properties": {
                    "ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of relevant document IDs.",
                    }
                },
                "required": ["ids"],
            },
            category="utility",
            skip_cache=True,
        )

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        return kwargs


class RAGSubAgent(BaseAgent):
    """ReAct loop implementation using LangGraph for AWS Bedrock/Claude."""

    def __init__(
        self,
        system_prompt: str | None = None,
        tool_registry: ToolRegistry | None = None,
    ) -> None:
        """Initialize ReAct agent with optional custom system prompt and registry.

        Args:
            system_prompt: Custom system prompt. If None, uses default
                          RAG_SUB_AGENT_SYSTEM_PROMPT.
            tool_registry: Pre-configured registry with RAG tools.
        """
        if tool_registry is None:
            raise ValueError("A configured ToolRegistry must be explicitly injected.")
        with contextlib.suppress(ValueError):
            # tool already registered
            tool_registry.register(FinalAnswerTool())

        resolved_prompt = system_prompt or RAG_SUB_AGENT_SYSTEM_PROMPT
        super().__init__(
            model_id=settings.rag_sub_agent.model_id,
            system_prompt=resolved_prompt,
            tool_registry=tool_registry,
        )

    def _build_graph(self) -> CompiledStateGraph[Any, Any, Any, Any]:
        """Build the ReAct state machine with think/act/finalize nodes."""
        workflow = StateGraph(RAGSubAgentState)

        workflow.add_node("think", self._think_node)
        workflow.add_node("act", ToolNode(self.lc_tools))
        workflow.add_node("finalize", self._finalize_node)

        workflow.set_entry_point("think")
        workflow.add_conditional_edges(
            "think",
            self._should_continue,
            {
                "continue": "act",
                "finalize": "finalize",
            },
        )

        workflow.add_edge("act", "think")
        workflow.add_edge("finalize", END)

        return workflow.compile()

    async def _think_node(self, state: RAGSubAgentState) -> dict[str, Any]:
        """Reasoning step: Claude analyzes the situation and decides next action.

        Orchestrates the thinking process by building messages, calling the LLM,
        and parsing the response into state updates.
        """
        logger.info(
            "rag_sub_think",
            request_id=state["request_id"],
            iteration=state["iteration"],
        )

        try:
            messages = self._build_llm_messages(state)
            cache = self._build_llm_cache_flags(messages, state)
            tool_choice = (
                "final_answer" if state["iteration"] == state["max_iterations"] - 1 else "any"
            )
            response = await self._call_llm(messages, cache, tool_choice=tool_choice)

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

            next_action = (
                "answer"
                if "final_answer" in [tc["function"]["name"] for tc in tool_calls]
                else "tool_use"
            )
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

            # Error: LLM stopped without requesting tools
            if response["finish_reason"] == "stop" and not tool_calls:
                updates["status"] = "failed"

            if next_action == "answer":
                # extract specified chunks
                final_tool_call = next(
                    tc for tc in tool_calls if tc["function"]["name"] == "final_answer"
                )
                updates["final_chunks_ids"] = json.loads(final_tool_call["function"]["arguments"])[
                    "ids"
                ]
                updates["status"] = "completed"

            logger.info(
                "rag_sub_think_complete",
                request_id=state["request_id"],
                iteration=state["iteration"],
                has_tool_calls=bool(tool_calls),
                has_final_answer="final_answer" in updates,
                tokens_used=response["tokens"]["total"],
            )

            return updates

        except Exception as e:
            logger.error(
                "rag_sub_think_error",
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

    def _build_llm_messages(self, state: RAGSubAgentState) -> list[dict[str, Any]]:
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
        messages = [
            {"role": "user", "content": message} for message in format_rag_react_prompt(state)
        ]
        return [
            {"role": "system", "content": self.system_prompt},
            *messages,
        ]

    def _build_llm_cache_flags(
        self, messages: list[dict[str, Any]], state: RAGSubAgentState
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
        self, state: RAGSubAgentState
    ) -> Literal["continue", "finalize", "max_iterations"]:
        """Route decision after the think node.

        Pure routing function — does not mutate state.
        """
        if state["status"] in ("failed", "completed"):
            return "finalize"

        if state["final_chunks_ids"] is not None:
            return "finalize"

        return "continue"

    def _finalize_node(self, state: RAGSubAgentState) -> dict[str, Any]:
        """Prepare the final response and set completion metadata."""
        logger.info(
            "rag_sub_finalize",
            request_id=state["request_id"],
            status=state["status"],
            iteration=state["iteration"],
        )

        updates: dict[str, Any] = {
            "completed_at": datetime.now(UTC),
        }
        if state["status"] == "running":
            updates["status"] = "completed"

        return updates

    async def run(
        self,
        agent_query: str,
        max_iterations: int = 10,
    ) -> RAGSubAgentState:
        """Run the ReAct loop for a main agent query.

        Args:
            agent_query: The agents's question or command.
            max_iterations: Safety limit on think/act cycles.

        Returns:
            Final RAGSubAgentState with answer, reasoning trace, and metadata.

        Raises:
            AgentExecutionError: If the graph fails unexpectedly.
        """
        logger.info(
            "rag_sub_agent_start",
            query=agent_query[:200],
            max_iterations=max_iterations,
        )

        initial_state = create_initial_state(
            agent_query=agent_query,
            max_iterations=max_iterations,
        )

        try:
            final_state = cast(RAGSubAgentState, await self.graph.ainvoke(initial_state))
        except Exception as e:
            logger.error(
                "rag_sub_agent_error",
                request_id=initial_state["request_id"],
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True,
            )
            raise AgentExecutionError(f"RAG sub-agent execution failed: {e}") from e

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
            "rag_sub_agent_complete",
            request_id=final_state["request_id"],
            status=final_state["status"],
            iterations=final_state["iteration"],
            tokens=total_tokens,
            cache_read_input_tokens=cache_read_tokens,
            cache_creation_input_tokens=cache_creation_tokens,
            thought_count=len(final_state["thoughts"]),
            tool_call_count=len(final_state.get("tool_calls", [])),
        )

        return final_state
