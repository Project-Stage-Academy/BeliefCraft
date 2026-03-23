from datetime import UTC, datetime

from app.models.agent_state import AgentState, ThoughtStep, ToolCall
from app.services.reasoning_trace_formatter import ReasoningTraceFormatter


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
        {
            "role": "assistant",
            "content": "<thinking>Check inventory</thinking>",
            "tool_calls": [
                {
                    "id": "tc_1",
                    "type": "function",
                    "function": {
                        "name": "get_inventory_data",
                        "arguments": '{"warehouse_id": "WH-001"}',
                    },
                }
            ],
        }
    ]
    state["tool_calls"] = [
        ToolCall(
            tool_name="get_inventory_data",
            arguments={"warehouse_id": "WH-001"},
            result={"items": [1, 2, 3]},
        )
    ]

    result = formatter.format(state)

    assert len(result) == 1
    assert result[0]["action"]["tool"] == "get_inventory_data"
    assert result[0]["observation"] == "Received 1 data points"


def test_formats_multi_action_iteration() -> None:
    formatter = ReasoningTraceFormatter()
    state = _base_state()
    state["thoughts"] = [ThoughtStep(thought="Collect diagnostics", next_action="tool_use")]
    state["messages"] = [
        {
            "role": "assistant",
            "content": "<thinking>Collect diagnostics</thinking>",
            "tool_calls": [
                {
                    "id": "tc_1",
                    "type": "function",
                    "function": {
                        "name": "get_inventory_data",
                        "arguments": '{"warehouse_id": "WH-001"}',
                    },
                },
                {
                    "id": "tc_2",
                    "type": "function",
                    "function": {
                        "name": "search_knowledge_base",
                        "arguments": '{"query": "inventory discrepancy"}',
                    },
                },
            ],
        }
    ]
    state["tool_calls"] = [
        ToolCall(
            tool_name="get_inventory_data",
            arguments={"warehouse_id": "WH-001"},
            result={"items": [1, 2, 3]},
        ),
        ToolCall(
            tool_name="search_knowledge_base",
            arguments={"query": "inventory discrepancy"},
            result={"documents": [{"id": "chunk-1"}]},
        ),
    ]

    result = formatter.format(state)

    assert len(result) == 1
    assert "action" not in result[0]
    assert len(result[0]["actions"]) == 2
    assert result[0]["actions"][0]["tool"] == "get_inventory_data"
    assert result[0]["actions"][1]["tool"] == "search_knowledge_base"
    assert result[0]["actions"][1]["observation"] == "Received 1 documents"
