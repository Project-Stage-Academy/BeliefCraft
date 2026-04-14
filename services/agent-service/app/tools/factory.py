"""Factory for creating agent-specific tool registries."""

from app.tools.base import BaseTool
from app.tools.orchestration_tools import CallEnvSubAgentTool
from app.tools.registration import register_code_tools, register_environment_tools
from app.tools.registry import ToolRegistry
from common.logging import get_logger

logger = get_logger(__name__)


class ToolRegistryFactory:

    @staticmethod
    def create_react_agent_registry(
        mcp_rag_tools: list[BaseTool] | None = None,
        skill_tools: list[BaseTool] | None = None,
        env_sub_registry: ToolRegistry | None = None,
    ) -> ToolRegistry:
        registry = ToolRegistry()

        register_code_tools(registry)
        logger.info("react_registry_loaded_sandbox_tool")

        if mcp_rag_tools:
            for tool in mcp_rag_tools:
                registry.register(tool)
            logger.info("react_registry_loaded_mcp_tools", count=len(mcp_rag_tools))

        if skill_tools:
            for tool in skill_tools:
                registry.register(tool)
            logger.info("react_registry_loaded_skill_tools", count=len(skill_tools))

        # Inject the sub-agent tool into the ReAct registry
        if env_sub_registry:
            registry.register(CallEnvSubAgentTool(env_registry=env_sub_registry))
            logger.info("react_registry_loaded_orchestration_tool")

        logger.info(
            "react_agent_registry_created",
            total_tools=len(registry.tools),
            rag_tools=len(mcp_rag_tools or []),
            skill_tools=len(skill_tools or []),
            has_orchestrator=bool(env_sub_registry),
        )

        return registry

    @staticmethod
    def create_env_sub_agent_registry() -> ToolRegistry:
        registry = ToolRegistry()
        register_environment_tools(registry)

        logger.info(
            "env_sub_agent_registry_created",
            total_tools=len(registry.tools),
        )

        return registry
