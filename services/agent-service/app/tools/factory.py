"""Factory for creating agent-specific tool registries.

This module provides factory methods to build pre-configured ToolRegistry
instances for each agent type:

- ReActAgent: RAG + Skill tools (no environment tools)
- EnvSubAgent: Environment tools only

Future: ReActAgent registry can be injected with a "call_env_sub_agent" tool
at startup to enable orchestration.

Example:
    ```python
    from app.tools.factory import ToolRegistryFactory

    # Create registries
    react_registry = ToolRegistryFactory.create_react_agent_registry()
    env_sub_registry = ToolRegistryFactory.create_env_sub_agent_registry()

    # Create agents
    react_agent = ReActAgent(tool_registry=react_registry)
    env_sub_agent = EnvSubAgent(tool_registry=env_sub_registry)
    ```
"""

from app.tools.base import BaseTool
from app.tools.cached_tool import CachedTool
from app.tools.environment_tools import (
    GetCapacityUtilizationSnapshotTool,
    GetDeviceAnomaliesTool,
    GetDeviceHealthSummaryTool,
    GetInventoryAdjustmentsSummaryTool,
    GetInventoryMoveAuditTraceTool,
    GetInventoryMoveTool,
    GetLocationsTreeTool,
    GetLocationTool,
    GetObservedInventorySnapshotTool,
    GetProcurementPipelineSummaryTool,
    GetPurchaseOrderTool,
    GetSensorDeviceTool,
    GetSupplierTool,
    GetWarehouseTool,
    ListInventoryMovesTool,
    ListLocationsTool,
    ListPOLinesTool,
    ListPurchaseOrdersTool,
    ListSensorDevicesTool,
    ListSuppliersTool,
    ListWarehousesTool,
)
from app.tools.registry import ToolRegistry
from common.logging import get_logger

logger = get_logger(__name__)


class ToolRegistryFactory:
    """Factory for creating agent-specific tool registries."""

    @staticmethod
    def create_react_agent_registry(
        mcp_rag_tools: list[BaseTool] | None = None,
        skill_tools: list[BaseTool] | None = None,
    ) -> ToolRegistry:
        """Create registry for ReActAgent with RAG + Skill tools.

        ReActAgent is the main orchestrator that handles user queries.
        It has access to:
        - RAG tools (semantic search, knowledge graph expansion)
        - Skill tools (domain expertise loading)
        - Future: call_env_sub_agent tool for environment planning

        Args:
            mcp_rag_tools: Optional pre-loaded RAG tools from MCP server
            skill_tools: Optional pre-loaded skill tools

        Returns:
            Configured ToolRegistry for ReActAgent
        """
        registry = ToolRegistry()

        if mcp_rag_tools:
            for tool in mcp_rag_tools:
                registry.register(tool)
            logger.info(
                "react_registry_loaded_mcp_tools",
                count=len(mcp_rag_tools),
            )

        if skill_tools:
            for tool in skill_tools:
                registry.register(tool)
            logger.info(
                "react_registry_loaded_skill_tools",
                count=len(skill_tools),
            )

        logger.info(
            "react_agent_registry_created",
            total_tools=len(registry.tools),
            rag_tools=len(mcp_rag_tools or []),
            skill_tools=len(skill_tools or []),
        )

        return registry

    @staticmethod
    def create_env_sub_agent_registry() -> ToolRegistry:
        """Create registry for EnvSubAgent with environment tools only.

        EnvSubAgent is a specialized agent for warehouse environment planning
        and monitoring. It has exclusive access to environment tools:

        PROCUREMENT (6): Suppliers, purchase orders, pipeline summary
        INVENTORY AUDIT (4): Moves, audit trace, adjustments
        TOPOLOGY (6): Warehouses, locations, capacity utilization
        DEVICE MONITORING (4): Sensor devices, health summary, anomalies
        OBSERVED INVENTORY (1): Real-time inventory snapshot

        Args:
            None

        Returns:
            Configured ToolRegistry for EnvSubAgent
        """
        registry = ToolRegistry()

        environment_tools: list[BaseTool] = [
            CachedTool(ListSuppliersTool()),
            CachedTool(GetSupplierTool()),
            CachedTool(ListPurchaseOrdersTool()),
            CachedTool(GetPurchaseOrderTool()),
            CachedTool(ListPOLinesTool()),
            CachedTool(GetProcurementPipelineSummaryTool()),
            CachedTool(ListInventoryMovesTool()),
            CachedTool(GetInventoryMoveTool()),
            CachedTool(GetInventoryMoveAuditTraceTool()),
            CachedTool(GetInventoryAdjustmentsSummaryTool()),
            CachedTool(ListWarehousesTool()),
            CachedTool(GetWarehouseTool()),
            CachedTool(ListLocationsTool()),
            CachedTool(GetLocationTool()),
            CachedTool(GetLocationsTreeTool()),
            CachedTool(GetCapacityUtilizationSnapshotTool()),
            CachedTool(ListSensorDevicesTool()),
            CachedTool(GetSensorDeviceTool()),
            CachedTool(GetDeviceHealthSummaryTool()),
            CachedTool(GetDeviceAnomaliesTool()),
            CachedTool(GetObservedInventorySnapshotTool()),
        ]

        for tool in environment_tools:
            registry.register(tool)

        logger.info(
            "env_sub_agent_registry_created",
            total_tools=len(registry.tools),
            environment_tools=len(environment_tools),
        )

        return registry
