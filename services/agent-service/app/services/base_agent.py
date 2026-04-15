"""Base agent class for LangGraph-based agents."""

from abc import ABC, abstractmethod
from typing import Any

from app.services.llm_service import LLMService
from app.tools.registry import ToolRegistry
from common.logging import get_logger
from langchain_core.tools import StructuredTool
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

        # Bind LangChain-compatible tools to the LLM automatically
        self.lc_tools = self._get_langchain_tools()
        if self.lc_tools:
            self.llm.llm = self.llm.llm.bind_tools(self.lc_tools)

        self.graph = self._build_graph()
        logger.info(
            "base_agent_initialized",
            agent_class=self.__class__.__name__,
            model_id=model_id,
            tools_count=len(tool_registry.tools),
        )

    def _get_langchain_tools(self) -> list[StructuredTool]:
        """Convert custom registry tools to LangChain StructuredTools."""
        lc_tools = []
        for tool in self.tool_registry.list_tools():
            lc_tools.append(
                StructuredTool.from_function(
                    func=tool.run,
                    name=tool.metadata.name,
                    description=tool.metadata.description,
                    args_schema=tool.metadata.parameters,
                    coroutine=tool.run,
                )
            )
        return lc_tools

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

    async def _call_llm(
        self,
        messages: list[dict[str, Any]],
        cache: list[bool] | None = None,
        tool_choice: str = "auto",
    ) -> dict[str, Any]:
        """Make the LLM API call with messages and tool definitions.

        Args:
            messages: List of messages to send to the LLM.
            cache: List with the same length as messages.
                   If cache[i] is True, messages[i] is written to cache.
            tool_choice: "any" - force any tool,
                         "name" - force tool called "name",
                         "auto" - don't force anything.

        Returns:
            LLM response dictionary containing message, tool_calls, tokens, etc.
        """
        return await self.llm.chat_completion(
            messages=messages, cache=cache, tool_choice=tool_choice
        )
