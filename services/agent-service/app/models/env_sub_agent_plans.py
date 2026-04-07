from typing import Any

from pydantic import BaseModel, Field


class PlannedToolCall(BaseModel):
    """A single API tool execution planned by the sub-agent."""

    rationale: str = Field(
        ...,
        description="A brief, 1-sentence explanation of why this "
        "specific tool is needed to help answer the user's query. "
        "Think step-by-step.",
    )
    tool_name: str = Field(
        ...,
        description="The exact name of the environment tool to execute. "
        "Must strictly match a tool from the registry "
        "(e.g., 'get_observed_inventory_snapshot', 'list_sensor_devices', "
        "'get_capacity_utilization_snapshot').",
    )
    arguments: dict[str, Any] = Field(
        default_factory=dict,
        description="A JSON dictionary of arguments required by the tool. "
        "Must exactly match the tool's parameter schema. "
        "Use empty dict {} if no arguments are needed.",
    )


class WarehousePlan(BaseModel):
    """The complete execution plan containing all tools needed to answer the query."""

    tool_calls: list[PlannedToolCall] = Field(
        default_factory=list,
        description="A list of independent tool calls to execute in parallel. "
        "Gather all necessary warehouse data in this single batch.",
    )
