"""
Tool registration logic.

Handles tool instantiation, caching wrappers, and MCP/Skill discovery.
Separated from __init__.py to prevent side effects and memory bloat on import.
"""

from typing import TYPE_CHECKING

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
from app.tools.mcp_loader import MCPToolLoader
from app.tools.mcp_tool import MCPClientProtocol
from app.tools.registry import ToolRegistry
from app.tools.skill_tools import LoadSkillTool, ReadSkillFilesTool
from common.logging import get_logger

if TYPE_CHECKING:
    from app.services.skill_store import SkillStore

logger = get_logger(__name__)

_global_skill_store: "SkillStore | None" = None


def get_skill_store() -> "SkillStore | None":
    return _global_skill_store


def register_environment_tools(registry: ToolRegistry) -> None:
    logger.info("registering_environment_tools_started")

    # PROCUREMENT MODULE (6 tools)
    registry.register(CachedTool(ListSuppliersTool()))
    registry.register(CachedTool(GetSupplierTool()))
    registry.register(CachedTool(ListPurchaseOrdersTool()))
    registry.register(CachedTool(GetPurchaseOrderTool()))
    registry.register(CachedTool(ListPOLinesTool()))
    registry.register(CachedTool(GetProcurementPipelineSummaryTool()))

    # INVENTORY AUDIT MODULE (4 tools)
    registry.register(CachedTool(ListInventoryMovesTool()))
    registry.register(CachedTool(GetInventoryMoveTool()))
    registry.register(CachedTool(GetInventoryMoveAuditTraceTool()))
    registry.register(CachedTool(GetInventoryAdjustmentsSummaryTool()))

    # TOPOLOGY MODULE (6 tools)
    registry.register(CachedTool(ListWarehousesTool()))
    registry.register(CachedTool(GetWarehouseTool()))
    registry.register(CachedTool(ListLocationsTool()))
    registry.register(CachedTool(GetLocationTool()))
    registry.register(CachedTool(GetLocationsTreeTool()))
    registry.register(CachedTool(GetCapacityUtilizationSnapshotTool()))

    # DEVICE MONITORING MODULE (4 tools) - Real-time, skip_cache=True
    registry.register(CachedTool(ListSensorDevicesTool()))
    registry.register(CachedTool(GetSensorDeviceTool()))
    registry.register(CachedTool(GetDeviceHealthSummaryTool()))
    registry.register(CachedTool(GetDeviceAnomaliesTool()))

    # OBSERVED INVENTORY MODULE (1 tool) - Real-time, skip_cache=True
    registry.register(CachedTool(GetObservedInventorySnapshotTool()))

    env_count = sum(
        1 for t in registry.tools.values() if t.get_metadata().category == "environment"
    )

    logger.info("environment_tools_registered", count=env_count)


async def register_mcp_rag_tools(mcp_client: MCPClientProtocol, registry: ToolRegistry) -> None:
    logger.info("registering_mcp_rag_tools_started")

    loader = MCPToolLoader(
        mcp_client=mcp_client,
        tool_registry=registry,
        wrap_with_cache=True,
        cache_ttl=86400,
        category_override="rag",
    )

    tools_count = await loader.load_tools()
    rag_count = sum(1 for t in registry.tools.values() if t.get_metadata().category == "rag")

    logger.info(
        "mcp_rag_tools_registered",
        discovered=tools_count,
        rag_category_count=rag_count,
        total_tools=len(registry.tools),
    )


def register_skill_tools(skills_dir: str, registry: ToolRegistry) -> None:
    global _global_skill_store
    from app.services.skill_store import SkillStore

    logger.info("registering_skill_tools_started", skills_dir=skills_dir)

    store = SkillStore(skills_dir=skills_dir)
    skills = store.scan()

    if not skills:
        logger.warning(
            "no_skills_found",
            skills_dir=skills_dir,
            message="Skills directory is empty or does not contain valid SKILL.md files",
        )

    _global_skill_store = store

    registry.register(CachedTool(LoadSkillTool(store)))
    registry.register(CachedTool(ReadSkillFilesTool(store)))

    skill_count = sum(
        1 for t in registry.tools.values() if t.get_metadata().category == "skill"
    )

    logger.info(
        "skill_tools_registered",
        skill_tools_count=skill_count,
        available_skills=list(skills.keys()),
        skills_count=len(skills),
        total_tools=len(registry.tools),
    )
