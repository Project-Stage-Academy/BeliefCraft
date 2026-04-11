from app.prompts.system_prompts import (
    REACT_LOOP_PROMPT_END,
    REACT_LOOP_PROMPT_START,
    WAREHOUSE_ADVISOR_SYSTEM_PROMPT,
    format_react_prompt,
    get_warehouse_advisor_prompt,
)
from langchain_core.messages import AIMessage, ToolMessage


class TestWarehouseAdvisorSystemPrompt:
    def test_contains_role_description(self) -> None:
        assert "warehouse operations advisor" in WAREHOUSE_ADVISOR_SYSTEM_PROMPT

    def test_contains_thinking_tag_instruction(self) -> None:
        assert "<thinking>" in WAREHOUSE_ADVISOR_SYSTEM_PROMPT

    def test_direct_evidence_constraints_override_default_template(self) -> None:
        assert "Follow the user's output constraints exactly" in WAREHOUSE_ADVISOR_SYSTEM_PROMPT
        assert "direct evidence from tools" in WAREHOUSE_ADVISOR_SYSTEM_PROMPT
        assert "omit algorithms, formulas, code snippets, and recommendations" in (
            WAREHOUSE_ADVISOR_SYSTEM_PROMPT
        )
        assert "unless the user explicitly requests them" in WAREHOUSE_ADVISOR_SYSTEM_PROMPT

    def test_contains_algorithm_references(self) -> None:
        assert "MDP" in WAREHOUSE_ADVISOR_SYSTEM_PROMPT
        assert "POMDP" in WAREHOUSE_ADVISOR_SYSTEM_PROMPT
        assert "Bayesian" in WAREHOUSE_ADVISOR_SYSTEM_PROMPT

    def test_contains_tool_categories(self) -> None:
        assert "Warehouse observation tools" in WAREHOUSE_ADVISOR_SYSTEM_PROMPT
        assert "Skill tools" in WAREHOUSE_ADVISOR_SYSTEM_PROMPT
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
        assert "{iteration}" in REACT_LOOP_PROMPT_END
        assert "{max_iterations}" in REACT_LOOP_PROMPT_END
        assert "{user_query}" in REACT_LOOP_PROMPT_START

    def test_contains_xml_tags(self) -> None:
        assert "<query>" in REACT_LOOP_PROMPT_START
        assert "</query>" in REACT_LOOP_PROMPT_START
        assert "<history>" in REACT_LOOP_PROMPT_START
        assert "</history>" in REACT_LOOP_PROMPT_END

    def test_contains_thinking_instruction(self) -> None:
        assert "<thinking>...</thinking>" in REACT_LOOP_PROMPT_END

    def test_contains_final_answer_instruction(self) -> None:
        assert "FINAL ANSWER:" in REACT_LOOP_PROMPT_END

    def test_is_nonempty_string(self) -> None:
        assert isinstance(REACT_LOOP_PROMPT_START, str)
        assert len(REACT_LOOP_PROMPT_START) > 0
        assert isinstance(REACT_LOOP_PROMPT_END, str)
        assert len(REACT_LOOP_PROMPT_END) > 0


class TestFormatReactPromptEmpty:
    """Tests for format_react_prompt with no history."""

    def test_empty_history(self) -> None:
        state = {
            "iteration": 1,
            "max_iterations": 10,
            "user_query": "What is the stock level?",
            "messages": [],
        }
        result = format_react_prompt(state)
        result_str = "\n".join(result)
        assert "1/10" in result_str
        assert "What is the stock level?" in result_str

    def test_empty_history_has_no_iteration_tags(self) -> None:
        state = {
            "iteration": 1,
            "max_iterations": 5,
            "user_query": "test query",
            "messages": [],
        }
        result = format_react_prompt(state)
        result_str = "\n".join(result)
        assert "<iteration" not in result_str

    def test_query_wrapped_in_xml(self) -> None:
        state = {
            "iteration": 1,
            "max_iterations": 5,
            "user_query": "Check warehouse status",
            "messages": [],
        }
        result = format_react_prompt(state)
        result_str = "\n".join(result)
        assert "<query>" in result_str
        assert "Check warehouse status" in result_str
        assert "</query>" in result_str


class TestFormatReactPromptWithThoughtSteps:
    """Tests for format_react_prompt using native LangChain messages."""

    def test_single_iteration_with_models(self) -> None:
        state = {
            "iteration": 2,
            "max_iterations": 10,
            "user_query": "What is the stock level?",
            "messages": [
                AIMessage(
                    content="<thinking>I need to check inventory</thinking>",
                    tool_calls=[
                        {
                            "id": "tc_1",
                            "name": "search_inventory",
                            "args": {"warehouse_id": "WH-001"},
                        }
                    ],
                ),
                ToolMessage(
                    tool_call_id="tc_1", name="search_inventory", content="", artifact={"stock": 42}
                ),
            ],
        }
        result = format_react_prompt(state)
        result_str = "\n".join(result)
        assert '<iteration index="1">' in result_str
        assert "<thinking>I need to check inventory</thinking>" in result_str
        assert '<action tool="search_inventory">' in result_str
        assert "<observation>" in result_str
        assert "42" in result_str

    def test_trace_meta_is_not_injected_into_prompt_history(self) -> None:
        state = {
            "iteration": 2,
            "max_iterations": 10,
            "user_query": "What is the stock level?",
            "messages": [
                AIMessage(
                    content="<thinking>I need to check inventory</thinking>",
                    tool_calls=[
                        {
                            "id": "tc_1",
                            "name": "search_inventory",
                            "args": {"warehouse_id": "WH-001"},
                        }
                    ],
                ),
                ToolMessage(
                    tool_call_id="tc_1",
                    name="search_inventory",
                    content="",
                    artifact={
                        "data": {"stock": 42},
                        "meta": {"count": 1, "filters": {"warehouse_id": "WH-001"}},
                    },
                ),
            ],
        }

        result = format_react_prompt(state)
        result_str = "\n".join(result)

        assert "'stock': 42" in result_str
        assert "'filters'" not in result_str
        assert "'count': 1" not in result_str

    def test_multiple_iterations(self) -> None:
        state = {
            "iteration": 3,
            "max_iterations": 10,
            "user_query": "Assess risk for item A",
            "messages": [
                AIMessage(
                    content="<thinking>Search for item A</thinking>",
                    tool_calls=[{"id": "tc_1", "name": "search", "args": {"item": "A"}}],
                ),
                ToolMessage(tool_call_id="tc_1", name="search", content="", artifact={"count": 10}),
                AIMessage(
                    content="<thinking>Now check risk</thinking>",
                    tool_calls=[
                        {"id": "tc_2", "name": "calculate_risk", "args": {"item": "A", "count": 10}}
                    ],
                ),
                ToolMessage(
                    tool_call_id="tc_2", name="calculate_risk", content="", artifact={"risk": 0.15}
                ),
            ],
        }
        result = format_react_prompt(state)
        result_str = "\n".join(result)
        assert '<iteration index="1">' in result_str
        assert '<iteration index="2">' in result_str
        assert "Search for item A" in result_str
        assert "Now check risk" in result_str
        assert '<action tool="search">' in result_str
        assert '<action tool="calculate_risk">' in result_str

    def test_tool_call_without_result(self) -> None:
        state = {
            "iteration": 1,
            "max_iterations": 5,
            "user_query": "test",
            "messages": [
                AIMessage(
                    content="<thinking>Try search</thinking>",
                    tool_calls=[{"id": "tc_1", "name": "search", "args": {"query": "test"}}],
                )
            ],
        }
        result = format_react_prompt(state)
        result_str = "\n".join(result)
        assert "<observation>" not in result_str
        assert '<action tool="search">' in result_str

    def test_single_iteration_renders_all_actions_from_same_assistant_turn(self) -> None:
        state = {
            "iteration": 2,
            "max_iterations": 10,
            "user_query": "Analyze discrepancy risk",
            "messages": [
                AIMessage(
                    content="<thinking>Collect warehouse diagnostics</thinking>",
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
            ],
        }

        result = format_react_prompt(state)
        result_str = "\n".join(result)

        assert result_str.count("<action tool=") == 2
        assert '<action tool="get_inventory_data">' in result_str
        assert '<action tool="search_knowledge_base">' in result_str
        assert "chunk-1" in result_str


class TestFormatReactPromptMessageEdgeCases:
    """Tests for edge cases parsing native LangChain messages."""

    def test_error_tool_message_renders_error_observation(self) -> None:
        state = {
            "iteration": 1,
            "max_iterations": 5,
            "user_query": "Check stock",
            "messages": [
                AIMessage(
                    content="<thinking>Check</thinking>",
                    tool_calls=[{"id": "tc_1", "name": "search", "args": {"q": "test"}}],
                ),
                ToolMessage(
                    tool_call_id="tc_1",
                    name="search",
                    content="API rate limit exceeded",
                    status="error",
                ),
            ],
        }
        result = format_react_prompt(state)
        result_str = "\n".join(result)
        assert '<action tool="search">' in result_str
        assert "<observation>{'error': 'API rate limit exceeded'}</observation>" in result_str

    def test_tool_message_without_artifact_falls_back_to_content(self) -> None:
        state = {
            "iteration": 1,
            "max_iterations": 5,
            "user_query": "Check stock",
            "messages": [
                AIMessage(
                    content="<thinking>Check</thinking>",
                    tool_calls=[{"id": "tc_1", "name": "search", "args": {"q": "test"}}],
                ),
                ToolMessage(
                    tool_call_id="tc_1",
                    name="search",
                    content="Plain text result",
                ),
            ],
        }
        result = format_react_prompt(state)
        result_str = "\n".join(result)
        assert "<observation>Plain text result</observation>" in result_str


class TestFormatReactPromptUnpairedThoughts:
    """Tests that thoughts without matching tool calls are included."""

    def test_final_thought_without_tool_call(self) -> None:
        """A trailing thought (e.g. final answer) must not be dropped."""
        state = {
            "iteration": 2,
            "max_iterations": 10,
            "user_query": "test",
            "messages": [
                AIMessage(
                    content="<thinking>Search first</thinking>",
                    tool_calls=[{"id": "t1", "name": "search", "args": {"q": "test"}}],
                ),
                ToolMessage(tool_call_id="t1", name="search", content="", artifact={"count": 5}),
                AIMessage(content="<thinking>Now I know the answer</thinking>"),
            ],
        }
        result = format_react_prompt(state)
        result_str = "\n".join(result)
        assert '<iteration index="1">' in result_str
        assert '<iteration index="2">' in result_str
        assert "Now I know the answer" in result_str
        # The first iteration should have thinking and action
        assert '<action tool="search">' in result_str


class TestFormatReactPromptIterationDisplay:
    """Tests that iteration counter renders correctly."""

    def test_iteration_counter_format(self) -> None:
        state = {
            "iteration": 3,
            "max_iterations": 7,
            "user_query": "test",
            "messages": [],
        }
        result = format_react_prompt(state)
        result_str = "\n".join(result)
        assert "3/7" in result_str

    def test_first_iteration(self) -> None:
        state = {
            "iteration": 1,
            "max_iterations": 10,
            "user_query": "test",
            "messages": [],
        }
        result = format_react_prompt(state)
        result_str = "\n".join(result)
        assert "1/10" in result_str

    def test_last_iteration(self) -> None:
        state = {
            "iteration": 10,
            "max_iterations": 10,
            "user_query": "test",
            "messages": [],
        }
        result = format_react_prompt(state)
        result_str = "\n".join(result)
        assert "10/10" in result_str


class TestGetWarehouseAdvisorPrompt:
    """Tests for get_warehouse_advisor_prompt dynamic prompt generation."""

    def test_without_skill_catalog(self) -> None:
        """Calling without skill_catalog should return base prompt."""
        result = get_warehouse_advisor_prompt()

        # Should contain core advisor role description
        assert "warehouse operations advisor" in result
        assert "CRITICAL INSTRUCTION" in result
        assert "<thinking>" in result

        # Should NOT contain skills catalog section
        assert "<skills_catalog>" not in result
        assert "</skills_catalog>" not in result

    def test_with_skill_catalog(self) -> None:
        """Calling with skill_catalog should inject catalog into prompt."""
        test_catalog = """<skill name="test-skill">
  <description>Test skill for verification</description>
  <tags>testing, verification</tags>
</skill>"""

        result = get_warehouse_advisor_prompt(skill_catalog=test_catalog)

        # Should contain injected catalog
        assert "<skills_catalog>" in result
        assert test_catalog in result
        assert "</skills_catalog>" in result

        # Should still contain core advisor content
        assert "warehouse operations advisor" in result

    def test_skill_catalog_xml_wrapping(self) -> None:
        """Skill catalog should be wrapped in XML tags."""
        test_catalog = "<skill>example</skill>"
        result = get_warehouse_advisor_prompt(skill_catalog=test_catalog)

        # Verify proper XML wrapping
        assert "<skills_catalog>\n" + test_catalog + "\n</skills_catalog>" in result

    def test_with_empty_skill_catalog(self) -> None:
        """Empty skill catalog should not add catalog section."""
        result = get_warehouse_advisor_prompt(skill_catalog="")

        # Empty string is falsy, so no catalog section should be added
        assert "<skills_catalog>" not in result
        assert "</skills_catalog>" not in result

    def test_backward_compatibility(self) -> None:
        """WAREHOUSE_ADVISOR_SYSTEM_PROMPT constant should remain unchanged."""
        # The constant should be the base prompt without skills
        assert "warehouse operations advisor" in WAREHOUSE_ADVISOR_SYSTEM_PROMPT
        assert "<skills_catalog>" not in WAREHOUSE_ADVISOR_SYSTEM_PROMPT

        # get_warehouse_advisor_prompt() without args should match the constant
        dynamic_base = get_warehouse_advisor_prompt()
        assert dynamic_base == WAREHOUSE_ADVISOR_SYSTEM_PROMPT

    def test_skill_catalog_placement(self) -> None:
        """Skill catalog should be placed in appropriate location."""
        test_catalog = "<skill>test</skill>"
        result = get_warehouse_advisor_prompt(skill_catalog=test_catalog)

        # Find positions in the prompt
        catalog_pos = result.find("<skills_catalog>")
        response_format_pos = result.find("Response format:")

        # Catalog should come before response format section
        if response_format_pos != -1:
            assert catalog_pos < response_format_pos
        else:
            # Catalog should still be present
            assert catalog_pos != -1


class TestReactPromptCachingPrefixStability:
    """Tests to protect append-only prompt growth assumptions for KV caching."""

    @staticmethod
    def _extract_history_from_list(prompt_list: list[str]) -> str:
        # history is the middle elements
        # REACT_LOOP_PROMPT_START ... iterations ... REACT_LOOP_PROMPT_END
        return "\n".join(prompt_list[1:-1])

    def test_history_prefix_is_stable_when_appending_iteration(self) -> None:
        base_state = {
            "iteration": 2,
            "max_iterations": 6,
            "user_query": "Analyze discrepancy risk",
            "messages": [
                AIMessage(
                    content="<thinking>Gather inventory deltas</thinking>",
                    tool_calls=[
                        {
                            "id": "tc_1",
                            "name": "list_inventory_moves",
                            "args": {"window": "24h"},
                        }
                    ],
                ),
                ToolMessage(
                    tool_call_id="tc_1",
                    name="list_inventory_moves",
                    content="",
                    artifact={"count": 4},
                ),
            ],
        }

        appended_state = {
            "iteration": 3,
            "max_iterations": 6,
            "user_query": "Analyze discrepancy risk",
            "messages": [
                AIMessage(
                    content="<thinking>Gather inventory deltas</thinking>",
                    tool_calls=[
                        {
                            "id": "tc_1",
                            "name": "list_inventory_moves",
                            "args": {"window": "24h"},
                        }
                    ],
                ),
                ToolMessage(
                    tool_call_id="tc_1",
                    name="list_inventory_moves",
                    content="",
                    artifact={"count": 4},
                ),
                AIMessage(
                    content="<thinking>Check device anomalies</thinking>",
                    tool_calls=[
                        {
                            "id": "tc_2",
                            "name": "list_device_alerts",
                            "args": {"severity": "high"},
                        }
                    ],
                ),
                ToolMessage(
                    tool_call_id="tc_2",
                    name="list_device_alerts",
                    content="",
                    artifact={"alerts": 1},
                ),
            ],
        }

        base_prompt = format_react_prompt(base_state)
        appended_prompt = format_react_prompt(appended_state)
        base_history = self._extract_history_from_list(base_prompt)
        appended_history = self._extract_history_from_list(appended_prompt)

        assert appended_history.startswith(base_history)
        assert '<iteration index="2">' in appended_history
        assert "Check device anomalies" in appended_history
        assert '<action tool="list_device_alerts">' in appended_history

    def test_overall_prompt_prefix_is_stable_when_appending_iteration(self) -> None:
        base_state = {
            "iteration": 2,
            "max_iterations": 6,
            "user_query": "Assess stockout exposure",
            "messages": [
                AIMessage(
                    content="<thinking>Query current stock</thinking>",
                    tool_calls=[
                        {
                            "id": "tc_1",
                            "name": "get_inventory_data",
                            "args": {"sku": "ABC-123"},
                        }
                    ],
                ),
                ToolMessage(
                    tool_call_id="tc_1",
                    name="get_inventory_data",
                    content="",
                    artifact={"on_hand": 12},
                ),
            ],
        }

        appended_state = {
            "iteration": 3,
            "max_iterations": 6,
            "user_query": "Assess stockout exposure",
            "messages": [
                AIMessage(
                    content="<thinking>Query current stock</thinking>",
                    tool_calls=[
                        {
                            "id": "tc_1",
                            "name": "get_inventory_data",
                            "args": {"sku": "ABC-123"},
                        }
                    ],
                ),
                ToolMessage(
                    tool_call_id="tc_1",
                    name="get_inventory_data",
                    content="",
                    artifact={"on_hand": 12},
                ),
                AIMessage(
                    content="<thinking>Estimate lead-time risk</thinking>",
                    tool_calls=[
                        {
                            "id": "tc_2",
                            "name": "get_supplier_lead_time",
                            "args": {"supplier": "S-9"},
                        }
                    ],
                ),
                ToolMessage(
                    tool_call_id="tc_2",
                    name="get_supplier_lead_time",
                    content="",
                    artifact={"days": 5},
                ),
            ],
        }

        base_prompt = format_react_prompt(base_state)
        appended_prompt = format_react_prompt(appended_state)

        # Check that the first two elements (start + first iteration) are the same
        assert base_prompt[0] == appended_prompt[0]
        assert base_prompt[1] == appended_prompt[1]

        full_appended_str = "\n".join(appended_prompt)
        assert "You are in a ReAct (Reasoning + Acting) loop." in full_appended_str
        assert "<query>" in full_appended_str
        assert "Current iteration: 3/6" in full_appended_str
