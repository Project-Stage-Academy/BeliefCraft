from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.models.env_sub_agent_plans import PlannedToolCall, WarehousePlan
from app.services.env_sub_agent import EnvSubAgent
from app.tools.base import ToolMetadata
from app.tools.registry import ToolRegistry


@pytest.fixture
def mock_registry() -> MagicMock:
    registry = MagicMock(spec=ToolRegistry)

    inventory_tool = MagicMock()
    inventory_tool.metadata = ToolMetadata(
        name="list_inventory_moves",
        description="Get inventory movement history",
        category="environment",
        parameters={"type": "object"},
    )

    observed_tool = MagicMock()
    observed_tool.metadata = ToolMetadata(
        name="get_observed_inventory_snapshot",
        description="Get observed inventory snapshot",
        category="environment",
        parameters={"type": "object"},
    )

    registry.list_tools.return_value = [inventory_tool, observed_tool]
    return registry


@pytest.fixture
def agent(mock_registry: MagicMock) -> EnvSubAgent:
    with patch("app.services.base_agent.LLMService"):
        return EnvSubAgent(tool_registry=mock_registry)


def _make_lc_tool(name: str, result: object) -> MagicMock:
    tool = MagicMock()
    tool.name = name
    tool.ainvoke = AsyncMock(return_value=result)
    return tool


@pytest.mark.asyncio
async def test_env_sub_agent_run_distills_inventory_discrepancy(agent: EnvSubAgent) -> None:
    agent.llm.structured_completion = AsyncMock(
        return_value=WarehousePlan(
            tool_calls=[
                PlannedToolCall(
                    rationale="Need system movement history",
                    tool_name="list_inventory_moves",
                    arguments={"product_id": "SKU-1"},
                ),
                PlannedToolCall(
                    rationale="Need physical observation snapshot",
                    tool_name="get_observed_inventory_snapshot",
                    arguments={"quality_status_in": ["good"]},
                ),
            ]
        )
    )

    inventory_result = MagicMock()
    inventory_result.success = True
    inventory_result.data = {
        "data": [
            {
                "move_id": "123e4567-e89b-12d3-a456-426614174000",
                "product_id": "SKU-1",
                "quantity": 10,
                "move_type": "transfer",
                "to_location_id": "WH-1-BIN-01",
            }
        ],
        "message": "Retrieved 1 inventory move.",
        "meta": {"count": 1, "trace_count": 1},
    }

    observed_result = MagicMock()
    observed_result.success = True
    observed_result.data = {
        "data": [
            {
                "product_id": "SKU-1",
                "location_code": "WH-1-BIN-01",
                "observed_quantity": 8,
                "quality_status": "good",
            }
        ],
        "message": "Retrieved 1 observed inventory row.",
        "meta": {"count": 1, "trace_count": 1},
    }

    agent.lc_tools = [
        _make_lc_tool("list_inventory_moves", inventory_result),
        _make_lc_tool("get_observed_inventory_snapshot", observed_result),
    ]

    agent.llm.chat_completion = AsyncMock(
        return_value={
            "message": {
                "role": "assistant",
                "content": (
                    "- System records show 10 units of SKU-1 moved into WH-1-BIN-01\n"
                    "- Observed inventory at WH-1-BIN-01 shows 8 units of SKU-1\n"
                    "- Discrepancy: physical stock is 2 units lower than system records"
                ),
            },
            "tool_calls": [],
            "finish_reason": "stop",
            "tokens": {"prompt": 20, "completion": 12, "total": 32},
        }
    )

    final_state = await agent.run("Check whether SKU-1 has an inventory discrepancy")

    assert final_state["status"] == "completed"
    assert final_state["plan"] is not None
    assert len(final_state["plan"].tool_calls) == 2
    assert final_state["observations"]
    assert final_state["state_summary"] is not None
    assert final_state["state_summary"].startswith("- ")
    assert "Discrepancy" in final_state["state_summary"]
    assert "123e4567-e89b-12d3-a456-426614174000" not in final_state["state_summary"]
    assert "raw JSON" not in final_state["state_summary"]
    assert final_state["completed_at"] is not None
    assert final_state["total_tokens"] == 32

#===================================================================================#

@pytest.mark.asyncio
async def test_env_sub_agent_run_distills_device_health_findings(agent: EnvSubAgent) -> None:
    agent.llm.structured_completion = AsyncMock(
        return_value=WarehousePlan(
            tool_calls=[
                PlannedToolCall(
                    rationale="Need device health information",
                    tool_name="get_device_health_summary",
                    arguments={"warehouse_id": "WH-1"},
                ),
                PlannedToolCall(
                    rationale="Need anomaly detection results",
                    tool_name="get_device_anomalies",
                    arguments={"warehouse_id": "WH-1", "window": 24},
                ),
            ]
        )
    )

    health_result = MagicMock()
    health_result.success = True
    health_result.data = {
        "data": [
            {
                "device_id": "sensor-abc-123",
                "device_type": "temperature",
                "status": "degraded",
                "health_score": 0.45,
                "last_seen_at": "2026-04-02T09:00:00Z",
            },
            {
                "device_id": "sensor-xyz-789",
                "device_type": "barcode",
                "status": "online",
                "health_score": 0.92,
                "last_seen_at": "2026-04-04T09:55:00Z",
            },
        ],
        "message": "Retrieved 2 device health records.",
        "meta": {"count": 2, "trace_count": 2},
    }

    anomalies_result = MagicMock()
    anomalies_result.success = True
    anomalies_result.data = {
        "data": [
            {
                "device_id": "sensor-abc-123",
                "anomaly_type": "stale_readings",
                "severity": "high",
                "details": "No recent scan in last 24 hours",
            }
        ],
        "message": "Detected 1 device anomaly.",
        "meta": {"count": 1, "trace_count": 1},
    }

    agent.lc_tools = [
        _make_lc_tool("get_device_health_summary", health_result),
        _make_lc_tool("get_device_anomalies", anomalies_result),
    ]

    agent.llm.chat_completion = AsyncMock(
        return_value={
            "message": {
                "role": "assistant",
                "content": (
                    "- Temperature sensor is in degraded condition with a 45% health score\n"
                    "- Temperature sensor has not reported recently and may be offline\n"
                    "- Barcode scanner is operating normally with a 92% health score\n"
                    "- Anomaly detected: one sensor is producing stale readings"
                ),
            },
            "tool_calls": [],
            "finish_reason": "stop",
            "tokens": {"prompt": 18, "completion": 14, "total": 32},
        }
    )

    final_state = await agent.run("Check whether any warehouse devices are unhealthy or anomalous")

    assert final_state["status"] == "completed"
    assert final_state["plan"] is not None
    assert len(final_state["plan"].tool_calls) == 2
    assert final_state["observations"]
    assert final_state["state_summary"] is not None
    assert final_state["state_summary"].startswith("- ")
    assert "degraded" in final_state["state_summary"].lower()
    assert "anomaly" in final_state["state_summary"].lower()
    assert "sensor-abc-123" not in final_state["state_summary"]
    assert final_state["completed_at"] is not None
    assert final_state["total_tokens"] == 32

#==============================================================================#

@pytest.mark.asyncio
async def test_env_sub_agent_run_handles_solver_failure(agent: EnvSubAgent) -> None:
    agent.llm.structured_completion = AsyncMock(
        return_value=WarehousePlan(
            tool_calls=[
                PlannedToolCall(
                    rationale="Need inventory movement history",
                    tool_name="list_inventory_moves",
                    arguments={"product_id": "SKU-1"},
                )
            ]
        )
    )

    inventory_result = MagicMock()
    inventory_result.success = True
    inventory_result.data = {
        "data": [
            {
                "move_id": "123e4567-e89b-12d3-a456-426614174000",
                "product_id": "SKU-1",
                "quantity": 10,
            }
        ],
        "message": "Retrieved 1 inventory move.",
        "meta": {"count": 1, "trace_count": 1},
    }
    agent.lc_tools = [_make_lc_tool("list_inventory_moves", inventory_result)]

    agent.llm.chat_completion = AsyncMock(side_effect=RuntimeError("solver LLM unavailable"))

    final_state = await agent.run("Check inventory discrepancy for SKU-1")

    assert final_state["status"] == "failed"
    assert final_state["error"] == "solver LLM unavailable"
    assert final_state["state_summary"] is not None
    assert final_state["state_summary"].startswith("- Solver processing failed:")
    assert final_state["observations"]
    assert final_state["plan"] is not None
    assert final_state["completed_at"] is not None

#===================================================================================#

@pytest.mark.asyncio
async def test_env_sub_agent_run_handles_empty_plan(agent: EnvSubAgent) -> None:
    agent.llm.structured_completion = AsyncMock(return_value=WarehousePlan(tool_calls=[]))

    final_state = await agent.run("Check inventory discrepancy for SKU-1")

    assert final_state["status"] == "failed"
    assert final_state["error"] == "No tools planned for execution"
    assert final_state["plan"] is not None
    assert final_state["plan"].tool_calls == []
    assert final_state["observations"] == {}
    assert final_state["state_summary"] is None
