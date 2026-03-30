from typing import Any

from app.config_load import settings
from app.models.env_sub_agent_state import ReWOOState
from app.prompts.env_sub_agent_system_prompts import ENV_SUB_AGENT_SYSTEM_PROMPT
from app.services.llm_service import LLMService
from common.logging import get_logger
from langgraph.graph import StateGraph
from langgraph.graph.state import CompiledStateGraph

logger = get_logger(__name__)


class EnvSubAgent:
    """ReWOO implementation using LangGraph for AWS Bedrock/Claude."""

    def __init__(self) -> None:
        """
        Initialize ReWOO agent.
        """

        self.llm: LLMService = LLMService(model_id=settings.env_sub_agent.model_id)
        self.system_prompt = ENV_SUB_AGENT_SYSTEM_PROMPT
        self.graph = self._build_graph()

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

    def _plan_node(self, state: ReWOOState) -> ReWOOState:
        """Planner node: Generate execution plan from agent query."""
        return state

    def _execute_node(self, state: ReWOOState) -> ReWOOState:
        """Executor node: Execute plan steps and update state."""
        return state

    def _solve_node(self, state: ReWOOState) -> ReWOOState:
        """Solver node: Solve a problem based on agent observations."""
        return state
