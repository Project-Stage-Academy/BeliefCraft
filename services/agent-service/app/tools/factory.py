"""Factory for creating agent-specific tool registries."""

from app.tools.base import BaseTool
from app.tools.registration import register_environment_tools
from app.tools.registry import ToolRegistry
from common.logging import get_logger

logger = get_logger(__name__)


class ToolRegistryFactory:

    @staticmethod
    def create_react_agent_registry(
        mcp_rag_tools: list[BaseTool] | None = None,
        skill_tools: list[BaseTool] | None = None,
    ) -> ToolRegistry:
        registry = ToolRegistry()

        if mcp_rag_tools:
            for tool in mcp_rag_tools:
                registry.register(tool)
            logger.info("react_registry_loaded_mcp_tools", count=len(mcp_rag_tools))

        if skill_tools:
            for tool in skill_tools:
                registry.register(tool)
            logger.info("react_registry_loaded_skill_tools", count=len(skill_tools))

        logger.info(
            "react_agent_registry_created",
            total_tools=len(registry.tools),
            rag_tools=len(mcp_rag_tools or []),
            skill_tools=len(skill_tools or []),
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
