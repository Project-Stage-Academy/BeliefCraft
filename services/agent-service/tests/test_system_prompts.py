from app.models.agent_state import ThoughtStep, ToolCall
from app.prompts.system_prompts import (
    REACT_LOOP_PROMPT,
    WAREHOUSE_ADVISOR_SYSTEM_PROMPT,
    format_react_prompt,
)


class TestWarehouseAdvisorSystemPrompt:
    def test_contains_role_description(self) -> None:
        assert "warehouse operations advisor" in WAREHOUSE_ADVISOR_SYSTEM_PROMPT

    def test_contains_thinking_tag_instruction(self) -> None:
        assert "<thinking>" in WAREHOUSE_ADVISOR_SYSTEM_PROMPT

    def test_contains_algorithm_references(self) -> None:
        assert "MDP" in WAREHOUSE_ADVISOR_SYSTEM_PROMPT
        assert "POMDP" in WAREHOUSE_ADVISOR_SYSTEM_PROMPT
        assert "Bayesian" in WAREHOUSE_ADVISOR_SYSTEM_PROMPT

    def test_contains_tool_categories(self) -> None:
        assert "Warehouse observation tools" in WAREHOUSE_ADVISOR_SYSTEM_PROMPT
        assert "Risk calculation tools" in WAREHOUSE_ADVISOR_SYSTEM_PROMPT
        assert "Knowledge base tools" in WAREHOUSE_ADVISOR_SYSTEM_PROMPT

    def test_contains_response_format(self) -> None:
        assert "Task summary" in WAREHOUSE_ADVISOR_SYSTEM_PROMPT
        assert "LaTeX" in WAREHOUSE_ADVISOR_SYSTEM_PROMPT
        assert "Python code snippet" in WAREHOUSE_ADVISOR_SYSTEM_PROMPT

    def test_is_nonempty_string(self) -> None:
        assert isinstance(WAREHOUSE_ADVISOR_SYSTEM_PROMPT, str)
        assert len(WAREHOUSE_ADVISOR_SYSTEM_PROMPT) > 0


class TestReactLoopPrompt:
    def test_contains_placeholders(self) -> None:
        assert "{iteration}" in REACT_LOOP_PROMPT
        assert "{max_iterations}" in REACT_LOOP_PROMPT
        assert "{user_query}" in REACT_LOOP_PROMPT
        assert "{history}" in REACT_LOOP_PROMPT

    def test_contains_xml_tags(self) -> None:
        assert "<query>" in REACT_LOOP_PROMPT
        assert "</query>" in REACT_LOOP_PROMPT
        assert "<history>" in REACT_LOOP_PROMPT
        assert "</history>" in REACT_LOOP_PROMPT

    def test_contains_thinking_instruction(self) -> None:
        assert "<thinking>...</thinking>" in REACT_LOOP_PROMPT

    def test_contains_final_answer_instruction(self) -> None:
        assert "FINAL ANSWER:" in REACT_LOOP_PROMPT

    def test_is_nonempty_string(self) -> None:
        assert isinstance(REACT_LOOP_PROMPT, str)
        assert len(REACT_LOOP_PROMPT) > 0


class TestFormatReactPromptEmpty:
    """Tests for format_react_prompt with no history."""

    def test_empty_history(self) -> None:
        state = {
            "iteration": 1,
            "max_iterations": 10,
            "user_query": "What is the stock level?",
            "thoughts": [],
            "tool_calls": [],
        }
        result = format_react_prompt(state)
        assert "1/10" in result
        assert "What is the stock level?" in result

    def test_empty_history_has_no_iteration_tags(self) -> None:
        state = {
            "iteration": 1,
            "max_iterations": 5,
            "user_query": "test query",
            "thoughts": [],
            "tool_calls": [],
        }
        result = format_react_prompt(state)
        assert "<iteration" not in result

    def test_query_wrapped_in_xml(self) -> None:
        state = {
            "iteration": 1,
            "max_iterations": 5,
            "user_query": "Check warehouse status",
            "thoughts": [],
            "tool_calls": [],
        }
        result = format_react_prompt(state)
        assert "<query>" in result
        assert "Check warehouse status" in result
        assert "</query>" in result


class TestFormatReactPromptWithThoughtSteps:
    """Tests for format_react_prompt with ThoughtStep model objects."""

    def test_single_iteration_with_models(self) -> None:
        thought = ThoughtStep(
            thought="I need to check inventory",
            reasoning="User asked about stock",
            next_action="call_search_tool",
        )
        tool_call = ToolCall(
            tool_name="search_inventory",
            arguments={"warehouse_id": "WH-001"},
            result={"stock": 42},
        )
        state = {
            "iteration": 2,
            "max_iterations": 10,
            "user_query": "What is the stock level?",
            "thoughts": [thought],
            "tool_calls": [tool_call],
        }
        result = format_react_prompt(state)
        assert '<iteration index="1">' in result
        assert "<thinking>I need to check inventory</thinking>" in result
        assert '<action tool="search_inventory">' in result
        assert "<observation>" in result
        assert "42" in result

    def test_multiple_iterations(self) -> None:
        thoughts = [
            ThoughtStep(
                thought="Search for item A",
                reasoning="Need data",
                next_action="search",
            ),
            ThoughtStep(
                thought="Now check risk",
                reasoning="Have data, assess risk",
                next_action="calculate",
            ),
        ]
        tool_calls = [
            ToolCall(
                tool_name="search",
                arguments={"item": "A"},
                result={"count": 10},
            ),
            ToolCall(
                tool_name="calculate_risk",
                arguments={"item": "A", "count": 10},
                result={"risk": 0.15},
            ),
        ]
        state = {
            "iteration": 3,
            "max_iterations": 10,
            "user_query": "Assess risk for item A",
            "thoughts": thoughts,
            "tool_calls": tool_calls,
        }
        result = format_react_prompt(state)
        assert '<iteration index="1">' in result
        assert '<iteration index="2">' in result
        assert "Search for item A" in result
        assert "Now check risk" in result
        assert '<action tool="search">' in result
        assert '<action tool="calculate_risk">' in result

    def test_tool_call_without_result(self) -> None:
        thought = ThoughtStep(
            thought="Try search",
            reasoning="Need info",
            next_action="search",
        )
        tool_call = ToolCall(
            tool_name="search",
            arguments={"query": "test"},
            result=None,
        )
        state = {
            "iteration": 1,
            "max_iterations": 5,
            "user_query": "test",
            "thoughts": [thought],
            "tool_calls": [tool_call],
        }
        result = format_react_prompt(state)
        assert "<observation>" not in result
        assert '<action tool="search">' in result


class TestFormatReactPromptWithDicts:
    """Tests for format_react_prompt with raw dict tool calls."""

    def test_dict_tool_call(self) -> None:
        thought = ThoughtStep(
            thought="Check stock",
            reasoning="User query",
            next_action="search",
        )
        tool_call = {
            "tool_name": "get_inventory",
            "arguments": {"sku": "ABC-123"},
            "result": {"quantity": 50},
        }
        state = {
            "iteration": 1,
            "max_iterations": 5,
            "user_query": "Check stock for ABC-123",
            "thoughts": [thought],
            "tool_calls": [tool_call],
        }
        result = format_react_prompt(state)
        assert '<action tool="get_inventory">' in result
        assert "<observation>" in result
        assert "50" in result

    def test_dict_tool_call_without_result(self) -> None:
        thought = ThoughtStep(
            thought="Check",
            reasoning="r",
            next_action="a",
        )
        tool_call = {
            "tool_name": "search",
            "arguments": {"q": "test"},
            "result": None,
        }
        state = {
            "iteration": 1,
            "max_iterations": 5,
            "user_query": "test",
            "thoughts": [thought],
            "tool_calls": [tool_call],
        }
        result = format_react_prompt(state)
        assert "<observation>" not in result


class TestFormatReactPromptUnpairedThoughts:
    """Tests that thoughts without matching tool calls are included."""

    def test_final_thought_without_tool_call(self) -> None:
        """A trailing thought (e.g. final answer) must not be dropped."""
        thoughts = [
            ThoughtStep(thought="Search first", next_action="tool_use"),
            ThoughtStep(thought="Now I know the answer", next_action="answer"),
        ]
        tool_calls = [
            ToolCall(
                tool_name="search",
                arguments={"q": "test"},
                result={"count": 5},
            ),
        ]
        state = {
            "iteration": 2,
            "max_iterations": 10,
            "user_query": "test",
            "thoughts": thoughts,
            "tool_calls": tool_calls,
        }
        result = format_react_prompt(state)
        assert '<iteration index="1">' in result
        assert '<iteration index="2">' in result
        assert "Now I know the answer" in result
        # The second iteration should have thinking but no action
        assert '<action tool="search">' in result


class TestFormatReactPromptIterationDisplay:
    """Tests that iteration counter renders correctly."""

    def test_iteration_counter_format(self) -> None:
        state = {
            "iteration": 3,
            "max_iterations": 7,
            "user_query": "test",
            "thoughts": [],
            "tool_calls": [],
        }
        result = format_react_prompt(state)
        assert "3/7" in result

    def test_first_iteration(self) -> None:
        state = {
            "iteration": 1,
            "max_iterations": 10,
            "user_query": "test",
            "thoughts": [],
            "tool_calls": [],
        }
        result = format_react_prompt(state)
        assert "1/10" in result

    def test_last_iteration(self) -> None:
        state = {
            "iteration": 10,
            "max_iterations": 10,
            "user_query": "test",
            "thoughts": [],
            "tool_calls": [],
        }
        result = format_react_prompt(state)
        assert "10/10" in result
