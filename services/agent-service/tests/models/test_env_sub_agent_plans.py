import pytest
from app.models.env_sub_agent_plans import PlannedToolCall, WarehousePlan
from pydantic import ValidationError


def test_planned_tool_call_valid() -> None:
    call = PlannedToolCall(
        rationale="Need to check stock", tool_name="get_inventory", arguments={"sku": "123"}
    )
    assert call.rationale == "Need to check stock"
    assert call.tool_name == "get_inventory"
    assert call.arguments == {"sku": "123"}


def test_planned_tool_call_default_arguments() -> None:
    call = PlannedToolCall(rationale="Check status", tool_name="get_status")
    assert call.arguments == {}


def test_planned_tool_call_missing_required() -> None:
    with pytest.raises(ValidationError):
        PlannedToolCall(tool_name="get_inventory")

    with pytest.raises(ValidationError):
        PlannedToolCall(rationale="Need to check stock")


def test_warehouse_plan_valid() -> None:
    call = PlannedToolCall(rationale="r", tool_name="t", arguments={})
    plan = WarehousePlan(tool_calls=[call])
    assert len(plan.tool_calls) == 1
    assert plan.tool_calls[0].tool_name == "t"


def test_warehouse_plan_default() -> None:
    plan = WarehousePlan()
    assert plan.tool_calls == []
