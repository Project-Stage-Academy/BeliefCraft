import asyncio
from typing import Any, cast

from app.config_load import settings
from app.core.exceptions import AgentExecutionError
from app.models.env_sub_agent_plans import PlannedToolCall, WarehousePlan
from app.models.env_sub_agent_state import ReWOOState, create_initial_state
from app.prompts.env_sub_agent_system_prompts import (
    ENV_SUB_AGENT_PLANNER_PROMPT,
    ENV_SUB_AGENT_SYSTEM_PROMPT,
)
from app.services.base_agent import BaseAgent
from app.tools.registry import ToolRegistry
from common.logging import get_logger
from langgraph.graph import StateGraph
from langgraph.graph.state import CompiledStateGraph

logger = get_logger(__name__)


class EnvSubAgent(BaseAgent):
    """ReWOO implementation using LangGraph for AWS Bedrock/Claude."""

    def __init__(
        self, system_prompt: str | None = None, tool_registry: ToolRegistry | None = None
    ) -> None:
        """Initialize ReWOO agent with environment-only tools."""
        if tool_registry is None:
            raise ValueError("A configured ToolRegistry must be explicitly injected.")

        resolved_prompt = system_prompt or ENV_SUB_AGENT_SYSTEM_PROMPT

        super().__init__(
            model_id=settings.env_sub_agent.model_id,
            system_prompt=resolved_prompt,
            tool_registry=tool_registry,
        )

    def _build_graph(self) -> CompiledStateGraph[Any, Any, Any, Any]:
        """Build ReWOO state machine with plan/execute/solve nodes."""
        workflow = StateGraph(ReWOOState)

        workflow.add_node("plan", self._plan_node)
        workflow.add_node("execute", self._execute_node)
        workflow.add_node("solve", self._solve_node)

        workflow.set_entry_point("plan")
        workflow.add_edge("plan", "execute")
        workflow.add_edge("execute", "solve")
        workflow.set_finish_point("solve")

        return workflow.compile()

    async def _plan_node(self, state: ReWOOState) -> dict[str, Any]:
        """Planner node: Generate structured execution plan from agent query."""
        request_id = state.get("request_id", "unknown")
        logger.info("env_sub_agent_plan_start", request_id=request_id)

        # 1. Format tool descriptions and parameters for the prompt
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
            # 2. Call LLM using structured output with the Pydantic schema
            plan_data = await self.llm.structured_completion(
                messages=messages, schema=WarehousePlan
            )

            # Ensure we have a valid WarehousePlan object
            if isinstance(plan_data, dict):
                plan_data = WarehousePlan(**plan_data)

            logger.info(
                "env_sub_agent_plan_success",
                request_id=request_id,
                planned_tools_count=len(plan_data.tool_calls),
            )

            return {"plan": plan_data, "status": "executing"}

        except Exception as e:
            logger.error(
                "env_sub_agent_plan_error",
                request_id=request_id,
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True,
            )
            return {"status": "failed", "error": str(e)}

    async def _execute_node(self, state: ReWOOState) -> dict[str, Any]:
        """Executor node: Execute all planned steps in parallel and collect observations."""
        request_id = state.get("request_id", "unknown")
        logger.info("env_sub_agent_execute_start", request_id=request_id)

        plan: WarehousePlan | None = state.get("plan")
        if not plan or not plan.tool_calls:
            logger.warning("env_sub_agent_empty_plan", request_id=request_id)
            return {"status": "failed", "error": "No tools planned for execution"}

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

    def _solve_node(self, state: ReWOOState) -> ReWOOState:
        """Solver node: Solve a problem based on agent observations."""
        return state

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
