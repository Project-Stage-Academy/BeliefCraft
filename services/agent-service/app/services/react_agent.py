"""ReAct agent implementation using LangGraph state machine."""

import json
from datetime import UTC, datetime
from typing import Any, Literal, cast

from app.core.exceptions import AgentExecutionError
from app.models.agent_state import AgentState, ThoughtStep, ToolCall, create_initial_state
from app.prompts.system_prompts import WAREHOUSE_ADVISOR_SYSTEM_PROMPT, format_react_prompt
from app.services.llm_service import LLMService
from app.tools.registry import tool_registry
from common.logging import get_logger
from langgraph.graph import END, StateGraph  # type: ignore[import-not-found]

logger = get_logger(__name__)


class ReActAgent:
    """ReAct loop implementation using LangGraph for AWS Bedrock/Claude."""

    def __init__(self) -> None:
        self.llm: LLMService = LLMService()
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        """Build the ReAct state machine with think/act/finalize nodes."""
        workflow = StateGraph(AgentState)

        workflow.add_node("think", self._think_node)
        workflow.add_node("act", self._act_node)
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

        try:
            messages = self._build_llm_messages(state)
            response = await self._call_llm(messages)
            return self._parse_and_update(state, response)

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
        XML history of prior thoughts/actions. Raw conversation messages
        are NOT appended separately to avoid duplicating context.

        Args:
            state: Current agent state.

        Returns:
            List of messages for LLM consumption.
        """
        return [
            {"role": "system", "content": WAREHOUSE_ADVISOR_SYSTEM_PROMPT},
            {"role": "user", "content": format_react_prompt(state)},  # type: ignore[arg-type]
        ]

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

    def _parse_and_update(self, state: AgentState, response: dict[str, Any]) -> dict[str, Any]:
        """Parse LLM response and build state updates.

        Extracts the assistant message, creates a thought step, and prepares
        state updates. Detects final answers when the LLM stops without
        requesting tools.

        Args:
            state: Current agent state.
            response: LLM response from chat_completion.

        Returns:
            Dictionary of state updates to merge into current state.
        """
        message_content = response["message"]["content"]

        # Store tool_calls on the assistant message so the act node
        # (and LLMService._convert_messages_to_langchain) can reconstruct
        # the full AIMessage with tool invocations.
        assistant_msg: dict[str, Any] = {
            "role": "assistant",
            "content": message_content,
        }
        if response["tool_calls"]:
            assistant_msg["tool_calls"] = response["tool_calls"]

        next_action = "tool_use" if response["tool_calls"] else "answer"
        thought = ThoughtStep(
            thought=message_content,
            next_action=next_action,
        )

        updates: dict[str, Any] = {
            "messages": state["messages"] + [assistant_msg],
            "thoughts": state["thoughts"] + [thought],
            "total_tokens": state["total_tokens"] + response["tokens"]["total"],
        }

        # Detect final answer: LLM stopped without requesting tools
        if response["finish_reason"] == "stop" and not response["tool_calls"]:
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
            has_tool_calls=bool(response["tool_calls"]),
            has_final_answer="final_answer" in updates,
            tokens_used=response["tokens"]["total"],
        )

        return updates

    async def _act_node(self, state: AgentState) -> dict[str, Any]:
        """Action step: execute tool calls from the last assistant message.

        Orchestrates tool execution by extracting pending calls, executing them,
        and building the updated state.
        """
        logger.info(
            "react_act",
            request_id=state["request_id"],
            iteration=state["iteration"],
        )

        pending_calls = self._extract_pending_tool_calls(state)
        results = await self._execute_all_tools(pending_calls, state["request_id"])
        return self._build_act_result(state, results)

    def _extract_pending_tool_calls(self, state: AgentState) -> list[dict[str, Any]]:
        """Extract tool calls from the last assistant message.

        Returns:
            List of tool call dictionaries with id, function name, and arguments.
        """
        last_message = state["messages"][-1] if state["messages"] else {}
        return cast(list[dict[str, Any]], last_message.get("tool_calls", []))

    async def _execute_all_tools(
        self, pending_calls: list[dict[str, Any]], request_id: str
    ) -> tuple[list[dict[str, Any]], list[ToolCall]]:
        """Execute all pending tool calls and collect results.

        Args:
            pending_calls: List of tool call dictionaries from the assistant message.
            request_id: Request ID for logging.

        Returns:
            Tuple of (new_messages, new_tool_calls) containing tool response messages
            and ToolCall objects.
        """
        new_messages: list[dict[str, Any]] = []
        new_tool_calls: list[ToolCall] = []

        for tool_call in pending_calls:
            func_name = tool_call["function"]["name"]
            tool_call_id = tool_call["id"]
            func_args = self._parse_tool_arguments(tool_call["function"]["arguments"])

            logger.info(
                "executing_tool",
                request_id=request_id,
                tool=func_name,
                tool_call_id=tool_call_id,
            )

            try:
                result = await self._execute_tool(func_name, func_args)

                new_tool_calls.append(
                    ToolCall(
                        tool_name=func_name,
                        arguments=func_args,
                        result=result,
                    )
                )
                new_messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "name": func_name,
                        "content": json.dumps(result),
                    }
                )

                logger.info(
                    "tool_execution_success",
                    request_id=request_id,
                    tool=func_name,
                    tool_call_id=tool_call_id,
                )

            except Exception as e:
                logger.error(
                    "tool_execution_error",
                    request_id=request_id,
                    tool=func_name,
                    tool_call_id=tool_call_id,
                    error=str(e),
                    error_type=type(e).__name__,
                    exc_info=True,
                )
                error_msg = f"Tool execution failed: {e}"
                new_tool_calls.append(
                    ToolCall(
                        tool_name=func_name,
                        arguments=func_args,
                        error=error_msg,
                    )
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

        return new_messages, new_tool_calls

    def _build_act_result(
        self,
        state: AgentState,
        results: tuple[list[dict[str, Any]], list[ToolCall]],
    ) -> dict[str, Any]:
        """Build the state update from tool execution results.

        Args:
            state: Current agent state.
            results: Tuple of (new_messages, new_tool_calls) from tool execution.

        Returns:
            State update dictionary with merged messages, tool calls, and incremented iteration.
        """
        new_messages, new_tool_calls = results
        return {
            "messages": state["messages"] + new_messages,
            "tool_calls": state["tool_calls"] + new_tool_calls,
            "iteration": state["iteration"] + 1,
        }

    @staticmethod
    def _parse_tool_arguments(raw_args: str | dict[str, Any]) -> dict[str, Any]:
        """Parse tool arguments from string or dict with fallback."""
        if isinstance(raw_args, dict):
            return raw_args
        try:
            return json.loads(raw_args)  # type: ignore[no-any-return]
        except (json.JSONDecodeError, TypeError):
            return {"query": raw_args}

    def _should_continue(
        self, state: AgentState
    ) -> Literal["continue", "finalize", "max_iterations"]:
        """Route decision after the think node.

        Pure routing function — does not mutate state.
        """
        if state["status"] in ("failed", "completed"):
            return "finalize"

        if state["final_answer"] is not None:
            return "finalize"

        if state["iteration"] >= state["max_iterations"]:
            logger.warning(
                "max_iterations_reached",
                request_id=state["request_id"],
                iteration=state["iteration"],
                max_iterations=state["max_iterations"],
            )
            return "max_iterations"

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

    async def _execute_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Execute a tool call using the registry.

        Args:
            tool_name: Name of the tool to invoke.
            arguments: Parsed arguments to pass to the tool.

        Returns:
            Dictionary with tool execution results or error information.
        """
        try:
            result = await tool_registry.execute_tool(tool_name, arguments)

            if result.success:
                return cast(dict[str, Any], result.data)
            else:
                return {
                    "error": result.error,
                    "message": f"Tool execution failed: {result.error}",
                }
        except Exception as e:
            logger.error("tool_execution_failed", tool=tool_name, error=str(e))
            return {
                "error": str(e),
                "message": f"Unexpected tool error: {str(e)}",
            }

    def _get_tool_definitions(self) -> list[dict[str, Any]]:
        """Get OpenAI function calling schemas for all tools."""
        return tool_registry.get_openai_functions()

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
            final_state: AgentState = await self.graph.ainvoke(initial_state)
        except Exception as e:
            logger.error(
                "react_agent_error",
                request_id=initial_state["request_id"],
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True,
            )
            raise AgentExecutionError(f"ReAct agent execution failed: {e}") from e

        logger.info(
            "react_agent_complete",
            request_id=final_state["request_id"],
            status=final_state["status"],
            iterations=final_state["iteration"],
            tokens=final_state["total_tokens"],
            thought_count=len(final_state["thoughts"]),
            tool_call_count=len(final_state["tool_calls"]),
        )

        return final_state
