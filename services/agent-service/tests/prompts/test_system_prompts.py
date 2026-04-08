from app.models.agent_state import ThoughtStep
from app.prompts.system_prompts import (
    REACT_LOOP_PROMPT,
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
            "messages": [],
        }
        result = format_react_prompt(state)
        assert "1/10" in result
        assert "What is the stock level?" in result

    def test_empty_history_has_no_iteration_tags(self) -> None:
        state = {
            "iteration": 1,
            "max_iterations": 5,
            "user_query": "test query",
            "messages": [],
        }
        result = format_react_prompt(state)
        assert "<iteration" not in result

    def test_query_wrapped_in_xml(self) -> None:
        state = {
            "iteration": 1,
            "max_iterations": 5,
            "user_query": "Check warehouse status",
            "messages": [],
        }
        result = format_react_prompt(state)
        assert "<query>" in result
        assert "Check warehouse status" in result
        assert "</query>" in result


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
        assert '<iteration index="1">' in result
        assert "<thinking>I need to check inventory</thinking>" in result
        assert '<action tool="search_inventory">' in result
        assert "<observation>" in result
        assert "42" in result

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

        assert "'stock': 42" in result
        assert "'filters'" not in result
        assert "'count': 1" not in result

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
        assert '<iteration index="1">' in result
        assert '<iteration index="2">' in result
        assert "Search for item A" in result
        assert "Now check risk" in result
        assert '<action tool="search">' in result
        assert '<action tool="calculate_risk">' in result

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
        assert "<observation>" not in result
        assert '<action tool="search">' in result

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

        assert result.count("<action tool=") == 2
        assert '<action tool="get_inventory_data">' in result
        assert '<action tool="search_knowledge_base">' in result
        assert "chunk-1" in result

    def test_langchain_message_history_includes_tool_observation(self) -> None:
        thought = ThoughtStep(
            thought="Need warehouse facts",
            reasoning="Need environment evidence",
            next_action="tool_use",
        )
        state = {
            "iteration": 2,
            "max_iterations": 10,
            "user_query": "Summarize inventory moves for PHA-22602565",
            "thoughts": [thought],
            "tool_calls": [],
            "messages": [
                AIMessage(
                    content="<thinking>Need warehouse facts</thinking>",
                    tool_calls=[
                        {
                            "name": "call_env_sub_agent",
                            "args": {"agent_query": "Summarize recent inventory moves"},
                            "id": "tc_1",
                        }
                    ],
                ),
                ToolMessage(
                    tool_call_id="tc_1",
                    name="call_env_sub_agent",
                    content='{"summary": "- Found 2 recent outbound moves"}',
                ),
            ],
        }

        result = format_react_prompt(state)

        assert '<action tool="call_env_sub_agent">' in result
        assert "<observation>" in result
        assert "Found 2 recent outbound moves" in result


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
        assert '<action tool="search">' in result
        assert "<observation>{'error': 'API rate limit exceeded'}</observation>" in result

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
        assert "<observation>Plain text result</observation>" in result


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
        assert '<iteration index="1">' in result
        assert '<iteration index="2">' in result
        assert "Now I know the answer" in result
        # The first iteration should have thinking and action
        assert '<action tool="search">' in result


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
        assert "3/7" in result

    def test_first_iteration(self) -> None:
        state = {
            "iteration": 1,
            "max_iterations": 10,
            "user_query": "test",
            "messages": [],
        }
        result = format_react_prompt(state)
        assert "1/10" in result

    def test_last_iteration(self) -> None:
        state = {
            "iteration": 10,
            "max_iterations": 10,
            "user_query": "test",
            "messages": [],
        }
        result = format_react_prompt(state)
        assert "10/10" in result


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
