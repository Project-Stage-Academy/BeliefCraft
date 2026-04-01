from app.models.agent_state import ThoughtStep, ToolCall
from app.prompts.system_prompts import (
    REACT_LOOP_PROMPT,
    WAREHOUSE_ADVISOR_SYSTEM_PROMPT,
    format_react_prompt,
    get_warehouse_advisor_prompt,
)


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

    def test_trace_meta_is_not_injected_into_prompt_history(self) -> None:
        thought = ThoughtStep(
            thought="I need to check inventory",
            reasoning="User asked about stock",
            next_action="call_search_tool",
        )
        tool_call = ToolCall(
            tool_name="search_inventory",
            arguments={"warehouse_id": "WH-001"},
            result={"stock": 42},
            trace_meta={"count": 1, "filters": {"warehouse_id": "WH-001"}},
        )
        state = {
            "iteration": 2,
            "max_iterations": 10,
            "user_query": "What is the stock level?",
            "thoughts": [thought],
            "tool_calls": [tool_call],
        }

        result = format_react_prompt(state)

        assert "'stock': 42" in result
        assert "'filters'" not in result
        assert "'count': 1" not in result

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

    def test_single_iteration_renders_all_actions_from_same_assistant_turn(self) -> None:
        thought = ThoughtStep(
            thought="Collect warehouse diagnostics",
            reasoning="Need both inventory and policy data",
            next_action="tool_use",
        )
        inventory_call = ToolCall(
            tool_name="get_inventory_data",
            arguments={"warehouse_id": "WH-001"},
            result={"items": [1, 2, 3]},
        )
        kb_call = ToolCall(
            tool_name="search_knowledge_base",
            arguments={"query": "inventory discrepancy"},
            result={"documents": [{"id": "chunk-1"}]},
        )
        state = {
            "iteration": 2,
            "max_iterations": 10,
            "user_query": "Analyze discrepancy risk",
            "thoughts": [thought],
            "tool_calls": [inventory_call, kb_call],
            "messages": [
                {
                    "role": "assistant",
                    "content": "<thinking>Collect warehouse diagnostics</thinking>",
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
            ],
        }

        result = format_react_prompt(state)

        assert result.count("<action tool=") == 2
        assert '<action tool="get_inventory_data">' in result
        assert '<action tool="search_knowledge_base">' in result
        assert "chunk-1" in result


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

    def test_dict_thought_uses_only_embedded_thought_text(self) -> None:
        state = {
            "iteration": 2,
            "max_iterations": 5,
            "user_query": "Analyze discrepancy risk",
            "thoughts": [
                {
                    "thought": "<thinking>Check recent moves</thinking>\nNeed device health next.",
                    "next_action": "tool_use",
                    "timestamp": "2026-03-17T11:32:33.498991Z",
                }
            ],
            "tool_calls": [
                {
                    "tool_name": "list_inventory_moves",
                    "arguments": {"from_ts": "2026-03-09T00:00:00Z"},
                    "result": {"data": {"moves": []}},
                }
            ],
            "messages": [
                {
                    "role": "assistant",
                    "content": "Check recent moves",
                    "tool_calls": [
                        {
                            "id": "tc_1",
                            "type": "function",
                            "function": {
                                "name": "list_inventory_moves",
                                "arguments": '{"from_ts": "2026-03-09T00:00:00Z"}',
                            },
                        }
                    ],
                }
            ],
        }

        result = format_react_prompt(state)

        assert "<thinking>Check recent moves</thinking>" in result
        assert "Need device health next." not in result
        assert "'next_action': 'tool_use'" not in result
        assert "'timestamp': '2026-03-17T11:32:33.498991Z'" not in result


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
    def _extract_history(prompt: str) -> str:
        start_tag = "<history>\n"
        end_tag = "\n</history>"
        start = prompt.index(start_tag) + len(start_tag)
        end = prompt.index(end_tag, start)
        return prompt[start:end]

    def test_history_prefix_is_stable_when_appending_iteration(self) -> None:
        base_state = {
            "iteration": 2,
            "max_iterations": 6,
            "user_query": "Analyze discrepancy risk",
            "thoughts": [
                ThoughtStep(
                    thought="Gather inventory deltas",
                    reasoning="Need recent movement context",
                    next_action="tool_use",
                )
            ],
            "tool_calls": [
                ToolCall(
                    tool_name="list_inventory_moves",
                    arguments={"window": "24h"},
                    result={"count": 4},
                )
            ],
        }

        appended_state = {
            "iteration": 3,
            "max_iterations": 6,
            "user_query": "Analyze discrepancy risk",
            "thoughts": [
                ThoughtStep(
                    thought="Gather inventory deltas",
                    reasoning="Need recent movement context",
                    next_action="tool_use",
                ),
                ThoughtStep(
                    thought="Check device anomalies",
                    reasoning="Need to explain movement spikes",
                    next_action="tool_use",
                ),
            ],
            "tool_calls": [
                ToolCall(
                    tool_name="list_inventory_moves",
                    arguments={"window": "24h"},
                    result={"count": 4},
                ),
                ToolCall(
                    tool_name="list_device_alerts",
                    arguments={"severity": "high"},
                    result={"alerts": 1},
                ),
            ],
        }

        base_prompt = format_react_prompt(base_state)
        appended_prompt = format_react_prompt(appended_state)
        base_history = self._extract_history(base_prompt)
        appended_history = self._extract_history(appended_prompt)

        assert appended_history.startswith(base_history)
        assert '<iteration index="2">' in appended_history
        assert "Check device anomalies" in appended_history
        assert '<action tool="list_device_alerts">' in appended_history

    def test_overall_prompt_prefix_is_stable_when_appending_iteration(self) -> None:
        base_state = {
            "iteration": 2,
            "max_iterations": 6,
            "user_query": "Assess stockout exposure",
            "thoughts": [
                ThoughtStep(
                    thought="Query current stock",
                    reasoning="Need baseline inventory",
                    next_action="tool_use",
                )
            ],
            "tool_calls": [
                ToolCall(
                    tool_name="get_inventory_data",
                    arguments={"sku": "ABC-123"},
                    result={"on_hand": 12},
                )
            ],
        }

        appended_state = {
            "iteration": 3,
            "max_iterations": 6,
            "user_query": "Assess stockout exposure",
            "thoughts": [
                ThoughtStep(
                    thought="Query current stock",
                    reasoning="Need baseline inventory",
                    next_action="tool_use",
                ),
                ThoughtStep(
                    thought="Estimate lead-time risk",
                    reasoning="Need fulfillment uncertainty",
                    next_action="tool_use",
                ),
            ],
            "tool_calls": [
                ToolCall(
                    tool_name="get_inventory_data",
                    arguments={"sku": "ABC-123"},
                    result={"on_hand": 12},
                ),
                ToolCall(
                    tool_name="get_supplier_lead_time",
                    arguments={"supplier": "S-9"},
                    result={"days": 5},
                ),
            ],
        }

        base_prompt = format_react_prompt(base_state)
        appended_prompt = format_react_prompt(appended_state)
        base_history = self._extract_history(base_prompt)

        prefix_through_base_history = base_prompt.split(base_history, 1)[0] + base_history

        assert appended_prompt.startswith(prefix_through_base_history)
        assert "You are in a ReAct (Reasoning + Acting) loop." in appended_prompt
        assert "<query>" in appended_prompt
        assert "Current iteration: 3/6" in appended_prompt
