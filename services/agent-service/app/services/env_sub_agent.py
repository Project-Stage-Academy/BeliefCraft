# file: services/agent-service/app/services/env_sub_agent.py
import json
from datetime import UTC, datetime
from typing import Any, Literal, cast

from app.config_load import settings
from app.core.exceptions import AgentExecutionError
from app.models.agent_state import merge_token_usage
from app.models.env_sub_agent_state import ReActState, create_initial_state
from app.prompts.env_sub_agent_system_prompts import ENV_SUB_AGENT_SYSTEM_PROMPT
from app.services.base_agent import BaseAgent
from app.services.message_parser import MessageParser
from app.tools.registry import ToolRegistry
from common.logging import get_logger
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode

logger = get_logger(__name__)


class EnvSubAgent(BaseAgent):
    def __init__(
        self,
        system_prompt: str | None = None,
        tool_registry: ToolRegistry | None = None,
        max_iterations: int = 15,
    ) -> None:
        if tool_registry is None:
            raise ValueError("A configured ToolRegistry must be explicitly injected.")

        super().__init__(
            model_id=settings.react_agent.model_id,
            system_prompt=system_prompt or ENV_SUB_AGENT_SYSTEM_PROMPT,
            tool_registry=tool_registry,
        )
        self.max_iterations = max_iterations

    def _build_graph(self) -> CompiledStateGraph[Any, Any, Any, Any]:
        workflow = StateGraph(ReActState)

        workflow.add_node("reason", self._reason_node)
        # Fix: Register ToolNode directly so LangGraph manages its configuration internally.
        workflow.add_node("act", ToolNode(self.lc_tools))

        workflow.set_entry_point("reason")
        workflow.add_conditional_edges(
            "reason",
            self._should_continue,
            {"continue": "act", "end": END},
        )
        workflow.add_edge("act", "reason")

        return workflow.compile()

    def _should_continue(self, state: ReActState) -> Literal["continue", "end"]:
        if state.get("status") == "failed":
            return "end"

        if state.get("step_count", 0) >= self.max_iterations:
            logger.warning(
                "env_sub_agent_iteration_limit_reached", request_id=state.get("request_id")
            )
            return "end"

        last_message = state["messages"][-1]
        if getattr(last_message, "tool_calls", None):
            return "continue"
        return "end"

    @staticmethod
    def _messages_to_dicts(messages: list[AnyMessage]) -> list[dict[str, Any]]:
        """Map LangChain messages to the raw dictionary format required by LLMService."""
        dict_messages: list[dict[str, Any]] = []

        for msg in messages:
            if isinstance(msg, SystemMessage):
                dict_messages.append({"role": "system", "content": str(msg.content)})
            elif isinstance(msg, HumanMessage):
                dict_messages.append({"role": "user", "content": str(msg.content)})
            elif isinstance(msg, AIMessage):
                # Leverage existing MessageParser to normalize tool calls into the OpenAI schema
                tool_calls = MessageParser._extract_message_tool_calls(msg)

                ai_msg_dict: dict[str, Any] = {
                    "role": "assistant",
                    "content": str(msg.content) if msg.content else "",
                    "tool_calls": tool_calls,
                }
                dict_messages.append(ai_msg_dict)
            elif isinstance(msg, ToolMessage):
                # Leverage existing MessageParser to safely handle artifacts and error states
                observation = MessageParser._extract_tool_message_observation(msg)
                content_str = (
                    json.dumps(observation) if isinstance(observation, dict) else str(observation)
                )

                tool_msg_dict: dict[str, Any] = {
                    "role": "tool",
                    "content": content_str,
                    "tool_call_id": str(msg.tool_call_id),
                    "name": str(msg.name),
                }
                dict_messages.append(tool_msg_dict)

        return dict_messages

    async def _reason_node(self, state: ReActState) -> dict[str, Any]:
        request_id = state.get("request_id", "unknown")

        messages = state.get("messages", [])
        if not messages:
            messages = [
                SystemMessage(content=self.system_prompt),
                HumanMessage(content=state["agent_query"]),
            ]

        dict_messages = self._messages_to_dicts(messages)

        try:
            response = await self._call_llm(dict_messages)

            tool_calls = response.get("tool_calls", [])
            ai_msg = AIMessage(
                content=response["message"].get("content", ""),
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

            token_usage = merge_token_usage(
                state.get("token_usage", {}),
                {response["model_id"]: response["tokens"]},
            )

            return {
                "messages": [ai_msg],
                "token_usage": token_usage,
                "step_count": state.get("step_count", 0) + 1,
            }

        except Exception as e:
            logger.error(
                "env_sub_agent_reason_error", request_id=request_id, error=str(e), exc_info=True
            )
            return {
                "status": "failed",
                "error": str(e),
                "completed_at": datetime.now(UTC),
            }

    async def run(self, agent_query: str, **kwargs: Any) -> ReActState:
        logger.info("env_sub_agent_run_start", query=agent_query[:200])
        initial_state = create_initial_state(agent_query=agent_query)

        try:
            final_state = cast(ReActState, await self.graph.ainvoke(initial_state))

            if final_state["status"] != "failed":
                if final_state.get("step_count", 0) >= self.max_iterations:
                    final_state["status"] = "failed"
                    final_state["error"] = (
                        f"Execution halted: Reached max iteration limit of {self.max_iterations}."
                    )
                else:
                    final_state["state_summary"] = str(final_state["messages"][-1].content)
                    final_state["status"] = "completed"

                final_state["completed_at"] = datetime.now(UTC)

            return final_state
        except Exception as e:
            logger.error("env_sub_agent_run_error", error=str(e), exc_info=True)
            raise AgentExecutionError(f"EnvSubAgent execution failed: {e}") from e
