from datetime import UTC, datetime

from app.models.agent_state import AgentState, ThoughtStep
from app.services.reasoning_trace_formatter import ReasoningTraceFormatter
from langchain_core.messages import AIMessage, ToolMessage


def _base_state() -> AgentState:
    return {
        "request_id": "req-formatter-001",
        "user_query": "Analyze discrepancy risk",
        "context": {},
        "iteration": 1,
        "max_iterations": 5,
        "thoughts": [],
        "tool_calls": [],
        "messages": [],
        "final_answer": None,
        "status": "completed",
        "error": None,
        "total_tokens": 0,
        "started_at": datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC),
        "completed_at": datetime(2026, 1, 1, 12, 0, 1, tzinfo=UTC),
    }


def test_formats_single_action_iteration() -> None:
    formatter = ReasoningTraceFormatter()
    state = _base_state()
    state["thoughts"] = [ThoughtStep(thought="Check inventory", next_action="tool_use")]
    state["messages"] = [
        AIMessage(
            content="<thinking>Check inventory</thinking>",
            tool_calls=[
                {
                    "id": "tc_1",
                    "name": "get_inventory_data",
                    "args": {"warehouse_id": "WH-001"},
                }
            ],
        ),
        ToolMessage(
            tool_call_id="tc_1",
            name="get_inventory_data",
            content="",
            artifact={"items": [1, 2, 3]},
        ),
    ]

    result = formatter.format(state)

    assert len(result) == 1
    assert result[0]["action"]["tool"] == "get_inventory_data"
    assert result[0]["observation"] == "Received 3 data points"


def test_formats_enveloped_list_payload_iteration() -> None:
    formatter = ReasoningTraceFormatter()
    state = _base_state()
    state["thoughts"] = [ThoughtStep(thought="Check observations", next_action="tool_use")]
    state["messages"] = [
        AIMessage(
            content="<thinking>Check observations</thinking>",
            tool_calls=[
                {
                    "id": "tc_1",
                    "name": "get_observed_inventory_snapshot",
                    "args": {},
                }
            ],
        ),
        ToolMessage(
            tool_call_id="tc_1",
            name="get_observed_inventory_snapshot",
            content="",
            artifact={
                "data": {"result": [{"id": "row-1"}, {"id": "row-2"}, {"id": "row-3"}]},
                "meta": {"count": 3},
            },
        ),
    ]

    result = formatter.format(state)

    assert result[0]["observation"] == "Received 3 data points"


def test_formats_enveloped_nested_list_payload_iteration() -> None:
    formatter = ReasoningTraceFormatter()
    state = _base_state()
    state["thoughts"] = [ThoughtStep(thought="Check moves", next_action="tool_use")]
    state["messages"] = [
        AIMessage(
            content="<thinking>Check moves</thinking>",
            tool_calls=[
                {
                    "id": "tc_1",
                    "name": "list_inventory_moves",
                    "args": {"from_ts": "2026-03-01T00:00:00Z"},
                }
            ],
        ),
        ToolMessage(
            tool_call_id="tc_1",
            name="list_inventory_moves",
            content="",
            artifact={"data": {"moves": [{"id": "m-1"}, {"id": "m-2"}]}, "meta": {"count": 2}},
        ),
    ]

    result = formatter.format(state)

    assert result[0]["observation"] == "Received 2 data points"


def test_formats_enveloped_single_object_payload_iteration() -> None:
    formatter = ReasoningTraceFormatter()
    state = _base_state()
    state["thoughts"] = [ThoughtStep(thought="Check location", next_action="tool_use")]
    state["messages"] = [
        AIMessage(
            content="<thinking>Check location</thinking>",
            tool_calls=[
                {
                    "id": "tc_1",
                    "name": "get_location",
                    "args": {"location_id": "loc-1"},
                }
            ],
        ),
        ToolMessage(
            tool_call_id="tc_1",
            name="get_location",
            content="",
            artifact={
                "data": {"location": {"id": "loc-1", "code": "WH-01-DOCK"}},
                "meta": {"count": 1, "location_id": "loc-1"},
            },
        ),
    ]

    result = formatter.format(state)

    assert result[0]["observation"] == "Received 1 data points"


def test_formats_enveloped_audit_trace_payload_iteration() -> None:
    formatter = ReasoningTraceFormatter()
    state = _base_state()
    state["thoughts"] = [ThoughtStep(thought="Check audit trace", next_action="tool_use")]
    state["messages"] = [
        AIMessage(
            content="<thinking>Check audit trace</thinking>",
            tool_calls=[
                {
                    "id": "tc_1",
                    "name": "get_inventory_move_audit_trace",
                    "args": {"move_id": "move-1"},
                }
            ],
        ),
        ToolMessage(
            tool_call_id="tc_1",
            name="get_inventory_move_audit_trace",
            content="",
            artifact={
                "data": {
                    "move": {"id": "move-1"},
                    "observations": [{"id": "obs-1"}, {"id": "obs-2"}],
                },
                "meta": {
                    "count": 3,
                    "move_id": "move-1",
                    "observation_count": 2,
                },
            },
        ),
    ]

    result = formatter.format(state)

    assert result[0]["observation"] == "Received 3 data points"


def test_formats_enveloped_tree_payload_iteration() -> None:
    formatter = ReasoningTraceFormatter()
    state = _base_state()
    state["thoughts"] = [ThoughtStep(thought="Check topology", next_action="tool_use")]
    state["messages"] = [
        AIMessage(
            content="<thinking>Check topology</thinking>",
            tool_calls=[
                {
                    "id": "tc_1",
                    "name": "get_locations_tree",
                    "args": {"warehouse_id": "wh-1"},
                }
            ],
        ),
        ToolMessage(
            tool_call_id="tc_1",
            name="get_locations_tree",
            content="",
            artifact={
                "data": {
                    "warehouse_id": "wh-1",
                    "warehouse_name": "WH-01",
                    "roots": [{"id": "root-1"}, {"id": "root-2"}],
                    "node_count": 5,
                    "root_count": 2,
                },
                "meta": {
                    "count": 5,
                    "warehouse_id": "wh-1",
                    "node_count": 5,
                    "root_count": 2,
                },
            },
        ),
    ]

    result = formatter.format(state)

    assert result[0]["observation"] == "Received 5 data points"


def test_formats_multi_action_iteration() -> None:
    formatter = ReasoningTraceFormatter()
    state = _base_state()
    state["thoughts"] = [ThoughtStep(thought="Collect diagnostics", next_action="tool_use")]
    state["messages"] = [
        AIMessage(
            content="<thinking>Collect diagnostics</thinking>",
            tool_calls=[
                {
                    "id": "tc_1",
                    "name": "get_inventory_data",
                    "args": {"warehouse_id": "WH-001"},
                },
                {
                    "id": "tc_2",
                    "name": "search_knowledge_base",
                    "args": {"query": "inventory discrepancy"},
                },
            ],
        ),
        ToolMessage(
            tool_call_id="tc_1",
            name="get_inventory_data",
            content="",
            artifact={"items": [1, 2, 3]},
        ),
        ToolMessage(
            tool_call_id="tc_2",
            name="search_knowledge_base",
            content="",
            artifact={"documents": [{"id": "chunk-1"}]},
        ),
    ]

    result = formatter.format(state)

    assert len(result) == 1
    assert "action" not in result[0]
    assert len(result[0]["actions"]) == 2
    assert result[0]["actions"][0]["tool"] == "get_inventory_data"
    assert result[0]["actions"][1]["tool"] == "search_knowledge_base"
    assert result[0]["actions"][1]["observation"] == "Received 1 documents"
