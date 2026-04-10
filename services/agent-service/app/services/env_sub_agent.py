import asyncio
import json
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, Literal, cast

from app.config_load import settings
from app.core.exceptions import AgentExecutionError
from app.models.env_sub_agent_plans import PlannedToolCall, WarehousePlan
from app.models.env_sub_agent_state import ReWOOState, create_initial_state
from app.prompts.env_sub_agent_system_prompts import (
    ENV_SUB_AGENT_PLANNER_PROMPT,
    ENV_SUB_AGENT_SOLVER_SYSTEM_PROMPT,
    ENV_SUB_AGENT_SYSTEM_PROMPT,
    SOLVER_SYSTEM_PROMPT,
)
from app.services.base_agent import BaseAgent
from app.services.llm_service import LLMService
from app.tools.registry import ToolRegistry
from common.logging import get_logger
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

logger = get_logger(__name__)


class EnvSubAgent(BaseAgent):
    """ReWOO implementation using LangGraph for AWS Bedrock/Claude."""

    _UUID_PATTERN = re.compile(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        flags=re.IGNORECASE,
    )
    _HEX_OBJECT_ID_PATTERN = re.compile(r"[0-9a-f]{24}", flags=re.IGNORECASE)

    def __init__(
        self, system_prompt: str | None = None, tool_registry: ToolRegistry | None = None
    ) -> None:
        """Initialize ReWOO agent with environment-only tools."""
        if tool_registry is None:
            raise ValueError("A configured ToolRegistry must be explicitly injected.")

        resolved_prompt = system_prompt or ENV_SUB_AGENT_SYSTEM_PROMPT

        super().__init__(
            model_id=settings.env_sub_agent.planner_model_id,
            system_prompt=resolved_prompt,
            tool_registry=tool_registry,
        )
        self.solver_llm = LLMService(model_id=settings.env_sub_agent.solver_model_id)

    def _build_graph(self) -> CompiledStateGraph[Any, Any, Any, Any]:
        """Build ReWOO state machine with plan/execute/solve nodes."""
        workflow = StateGraph(ReWOOState)

        workflow.add_node("plan", self._plan_node)
        workflow.add_node("execute", self._execute_node)
        workflow.add_node("solve", self._solve_node)

        workflow.set_entry_point("plan")
        workflow.add_edge("plan", "execute")
        workflow.add_conditional_edges(
            "execute",
            self._route_after_execute,
            {
                "solve": "solve",
                "end": END,
            },
        )
        workflow.add_edge("solve", END)

        return workflow.compile()

    @staticmethod
    def _route_after_execute(state: ReWOOState) -> Literal["solve", "end"]:
        """Skip the solver when execution has already failed."""
        return "end" if state.get("status") == "failed" else "solve"

    async def _plan_node(self, state: ReWOOState) -> dict[str, Any]:
        """Planner node: Generate structured execution plan from agent query."""
        request_id = state.get("request_id", "unknown")
        logger.info("env_sub_agent_plan_start", request_id=request_id)

        tool_descriptions = "\n".join(
            (
                f"- {tool.metadata.name}: {tool.metadata.description}\n"
                f"Parameters: {tool.metadata.parameters}"
            )
            for tool in self.tool_registry.list_tools()
        )

        user_prompt = ENV_SUB_AGENT_PLANNER_PROMPT.format(
            tool_descriptions=tool_descriptions, agent_query=state.get("agent_query", "")
        )

        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        try:
            plan_response = await self.llm.structured_completion(
                messages=messages,
                schema=WarehousePlan,
                include_usage=True,
            )
            if isinstance(plan_response, dict) and "result" in plan_response:
                plan_data = plan_response["result"]
                planner_tokens = plan_response.get("tokens", {}).get("total", 0)
            else:
                plan_data = plan_response
                planner_tokens = 0
            current_tokens = state.get("total_tokens", 0)

            if isinstance(plan_data, dict):
                plan_data = WarehousePlan(**plan_data)

            logger.info(
                "env_sub_agent_plan_success",
                request_id=request_id,
                planned_tools_count=len(plan_data.tool_calls),
            )

            return {
                "plan": plan_data,
                "status": "executing",
                "total_tokens": current_tokens + planner_tokens,
            }

        except Exception as e:
            logger.error(
                "env_sub_agent_plan_error",
                request_id=request_id,
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True,
            )
            return {
                "status": "failed",
                "error": str(e),
                "completed_at": datetime.now(UTC),
            }

    async def _execute_node(self, state: ReWOOState) -> dict[str, Any]:
        """Executor node: Execute all planned steps in parallel and collect observations."""
        request_id = state.get("request_id", "unknown")
        logger.info("env_sub_agent_execute_start", request_id=request_id)

        plan: WarehousePlan | None = state.get("plan")
        if not plan or not plan.tool_calls:
            logger.warning("env_sub_agent_empty_plan", request_id=request_id)
            return {
                "status": "failed",
                "error": "No tools planned for execution",
                "completed_at": datetime.now(UTC),
            }

        # Map LangChain tools by name for quick lookup
        lc_tool_map = {t.name: t for t in self.lc_tools}

        async def _invoke_lc_tool(call: PlannedToolCall) -> dict[str, Any]:
            tool = lc_tool_map.get(call.tool_name)
            if not tool:
                return {
                    "status": "error",
                    "error": f"Tool {call.tool_name} not found",
                    "message": f"Tool {call.tool_name} not found",
                }

            # Let exceptions bubble up to asyncio.gather so it can format unhandled exceptions
            result = await tool.ainvoke(call.arguments)

            if result.success:
                return {"status": "success", "data": result.data}

            return {
                "status": "error",
                "error": result.error,
                "message": f"Tool execution failed: {result.error}",
            }

        tasks = [_invoke_lc_tool(call) for call in plan.tool_calls]

        # Execute all independent tools in parallel
        results = await asyncio.gather(*tasks, return_exceptions=True)

        observations: dict[str, Any] = {}
        safe_result: dict[str, Any] | BaseException
        for index, (call, result) in enumerate(zip(plan.tool_calls, results, strict=True)):
            if isinstance(result, Exception):
                safe_result = {
                    "status": "error",
                    "error": str(result),
                    "message": f"Unhandled exception: {type(result).__name__}",
                }
            else:
                safe_result = result

            # Append index to key to prevent overwriting if the same tool is called multiple times
            observations[f"{call.tool_name}_{index}"] = {
                "tool": call.tool_name,
                "arguments": call.arguments,
                "response": safe_result,
            }

        logger.info(
            "env_sub_agent_execute_success",
            request_id=request_id,
            executed_tools_count=len(plan.tool_calls),
        )

        return {"observations": observations, "status": "solving"}

    async def _solve_node(self, state: ReWOOState) -> dict[str, Any]:
        """Distill raw executor observations into a clean factual summary."""
        request_id = state.get("request_id", "unknown")

        logger.info(
            "solver_node_start",
            request_id=request_id,
            has_observations=bool(state.get("observations")),
        )

        if not state.get("observations"):
            logger.warning("solver_no_observations", request_id=request_id)
            return {
                "state_summary": "- No observations were collected\n"
                "- Insufficient data to provide summary",
                "status": "completed",
                "completed_at": datetime.now(UTC),
            }

        try:
            observations = self._sanitize_observations_for_solver(state["observations"])
            observations_str = json.dumps(observations, indent=2, ensure_ascii=False)

            plan_obj = state.get("plan")
            if plan_obj and hasattr(plan_obj, "tool_calls"):
                plan_lines = [
                    f"- {call.tool_name}({call.arguments})" for call in plan_obj.tool_calls
                ]
                plan_str = "\n".join(plan_lines) if plan_lines else "No tools planned"
            else:
                plan_str = "No plan available"

            user_prompt = SOLVER_SYSTEM_PROMPT.format(
                agent_query=state.get("agent_query", ""),
                plan=plan_str,
                observations=observations_str,
            )

            messages = [
                {"role": "system", "content": ENV_SUB_AGENT_SOLVER_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ]

            logger.debug(
                "solver_calling_llm",
                request_id=request_id,
                observations_length=len(observations_str),
            )

            response = await self.solver_llm.chat_completion(messages=messages)
            summary = response["message"]["content"].strip()
            tokens_used = response["tokens"]["total"]
            current_tokens = state.get("total_tokens", 0)

            if summary.startswith("```"):
                lines = summary.split("\n")
                summary = "\n".join(
                    line for line in lines if not line.strip().startswith("```")
                ).strip()

            summary = self._sanitize_summary(summary)

            if not summary or len(summary) < 10:
                logger.warning("solver_empty_response", request_id=request_id)
                summary = (
                    "- Unable to distill observations into a meaningful summary\n"
                    f"- Original query: {state.get('agent_query', 'unknown')}"
                )

            if not any(line.strip().startswith("-") for line in summary.split("\n")):
                logger.warning("solver_missing_bullets", request_id=request_id)
                summary = self._ensure_bullets(summary)

            logger.info(
                "solver_completed",
                request_id=request_id,
                summary_length=len(summary),
                summary_lines=summary.count("\n") + 1,
                tokens_used=tokens_used,
            )

            return {
                "state_summary": summary,
                "status": "completed",
                "completed_at": datetime.now(UTC),
                "total_tokens": current_tokens + tokens_used,
            }

        except Exception as e:
            logger.error(
                "solver_failed",
                request_id=request_id,
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True,
            )

            return {
                "state_summary": f"- Solver processing failed: {type(e).__name__}",
                "status": "failed",
                "completed_at": datetime.now(UTC),
                "total_tokens": state.get("total_tokens", 0),
                "error": str(e),
            }

    @staticmethod
    def _sanitize_observations_for_solver(payload: Any) -> Any:
        """Replace opaque internal identifiers with stable aliases before solver prompting."""
        alias_registry: dict[str, str] = {}
        alias_counters: dict[str, int] = {}
        return EnvSubAgent._sanitize_payload_node(payload, alias_registry, alias_counters)

    @staticmethod
    def _sanitize_payload_node(
        payload: Any,
        alias_registry: dict[str, str],
        alias_counters: dict[str, int],
        parent_key: str | None = None,
    ) -> Any:
        if isinstance(payload, Mapping):
            sanitized: dict[Any, Any] = {}
            for key, value in payload.items():
                child_key = key if isinstance(key, str) else None
                sanitized[key] = EnvSubAgent._sanitize_payload_node(
                    value,
                    alias_registry,
                    alias_counters,
                    parent_key=child_key,
                )
            return sanitized

        if isinstance(payload, list):
            return [
                EnvSubAgent._sanitize_payload_node(
                    item,
                    alias_registry,
                    alias_counters,
                    parent_key=parent_key,
                )
                for item in payload
            ]

        if isinstance(payload, str) and EnvSubAgent._should_alias_identifier(parent_key, payload):
            return EnvSubAgent._alias_identifier(
                parent_key or "id",
                payload,
                alias_registry,
                alias_counters,
            )

        return payload

    @staticmethod
    def _should_alias_identifier(key: str | None, value: str) -> bool:
        if not key:
            return EnvSubAgent._is_internal_identifier(value)

        if not re.fullmatch(r"[a-zA-Z_]*?(?:id|uuid)", key, flags=re.IGNORECASE):
            return False

        return EnvSubAgent._is_internal_identifier(value)

    @staticmethod
    def _is_internal_identifier(value: str) -> bool:
        return bool(
            EnvSubAgent._UUID_PATTERN.fullmatch(value)
            or EnvSubAgent._HEX_OBJECT_ID_PATTERN.fullmatch(value)
        )

    @staticmethod
    def _alias_identifier(
        key: str,
        value: str,
        alias_registry: dict[str, str],
        alias_counters: dict[str, int],
    ) -> str:
        alias_key = f"{key.lower()}::{value}"
        existing_alias = alias_registry.get(alias_key)
        if existing_alias:
            return existing_alias

        prefix = EnvSubAgent._alias_prefix_for_key(key)
        alias_counters[prefix] = alias_counters.get(prefix, 0) + 1
        alias = f"[{prefix}_{alias_counters[prefix]}]"
        alias_registry[alias_key] = alias
        return alias

    @staticmethod
    def _alias_prefix_for_key(key: str) -> str:
        normalized = key.lower()
        if "product" in normalized:
            return "PRODUCT"
        if "location" in normalized:
            return "LOC"
        if "warehouse" in normalized:
            return "WH"
        if "device" in normalized:
            return "DEVICE"
        if "move" in normalized:
            return "MOVE"
        return "ID"

    @staticmethod
    def _sanitize_summary(text: str) -> str:
        """Remove obvious technical identifiers from the solver summary."""
        text = re.sub(
            EnvSubAgent._UUID_PATTERN,
            "[ID]",
            text,
        )
        text = re.sub(EnvSubAgent._HEX_OBJECT_ID_PATTERN, "[ID]", text)
        text = re.sub(
            r"\b([a-zA-Z_]*?(?:id|uuid))\b\s*([:=])\s*([^\s,]+)",
            lambda match: EnvSubAgent._sanitize_summary_identifier(match),
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n\s*\n", "\n", text)
        text = re.sub(r"\s*,\s*,", ", ", text)
        text = re.sub(r"^\s*[-*]\s*,", "-", text, flags=re.MULTILINE)
        return text.strip()

    @staticmethod
    def _sanitize_summary_identifier(match: re.Match[str]) -> str:
        key, separator, value = match.groups()
        if EnvSubAgent._is_internal_identifier(value):
            return f"{key}{separator} [ID]"
        return match.group(0)

    @staticmethod
    def _ensure_bullets(text: str) -> str:
        """Convert free-form text into one-fact-per-line bullet points."""
        chunks = re.split(r"[.!?]\s+|\n+", text)
        bullets: list[str] = []

        for chunk in chunks:
            cleaned = chunk.strip()
            if cleaned and len(cleaned) > 5:
                bullets.append(cleaned if cleaned.startswith("-") else f"- {cleaned}")

        if not bullets:
            return f"- {text.strip()}"

        return "\n".join(bullets)

    async def run(self, agent_query: str, **kwargs: Any) -> ReWOOState:
        """Run the ReWOO loop for an agent query.

        Args:
            agent_query: The query outlining what data to retrieve.
            **kwargs: Optional metadata.

        Returns:
            Final ReWOOState with data retrieval plan and observations.

        Raises:
            AgentExecutionError: If the graph fails unexpectedly.
        """
        logger.info("env_sub_agent_run_start", query=agent_query[:200])

        initial_state = create_initial_state(agent_query=agent_query)
        try:
            final_state = cast(ReWOOState, await self.graph.ainvoke(initial_state))
        except Exception as e:
            logger.error(
                "env_sub_agent_run_error",
                request_id=initial_state["request_id"],
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True,
            )
            raise AgentExecutionError(f"EnvSubAgent execution failed: {e}") from e

        logger.info(
            "env_sub_agent_run_complete",
            request_id=final_state["request_id"],
            status=final_state["status"],
            tokens=final_state["total_tokens"],
        )
        return final_state
