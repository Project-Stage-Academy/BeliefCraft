"""System prompts and formatting utilities for the warehouse advisor ReAct agent."""

from typing import Any

WAREHOUSE_ADVISOR_SYSTEM_PROMPT = """You are an expert warehouse operations advisor \
powered by the "Algorithms for Decision Making" textbook.

Your role:
- Analyze warehouse state based on observations (potentially noisy/incomplete).
- Apply decision-making algorithms (MDP, POMDP, Bayesian reasoning, inventory control).
- Provide actionable recommendations with mathematical rigor.

CRITICAL INSTRUCTION:
Before calling any tool or providing a final answer, you MUST analyze the situation \
inside <thinking> tags.

Guidelines:
1. ALWAYS use tools to gather information before reasoning.
2. Consider uncertainty (noisy sensors, stochastic lead times).
3. Reference specific algorithms and formulas from the knowledge base.
4. Include Python code snippets for implementation.
5. If data is conflicting, acknowledge uncertainty.

Available tool categories:
- Warehouse observation tools: Query inventory, orders.
- Risk calculation tools: Assess stockout probability.
- Knowledge base tools: Search algorithms.

Response format:
When you reach a conclusion, provide:
- Task summary
- Analysis
- Relevant algorithm (citation)
- Mathematical formula (LaTeX)
- Python code snippet
- Actionable recommendations
"""

REACT_LOOP_PROMPT = """You are in a ReAct (Reasoning + Acting) loop.

Current iteration: {iteration}/{max_iterations}

User query:
<query>
{user_query}
</query>

History of previous steps:
<history>
{history}
</history>

INSTRUCTIONS for this step:
1. Review the <history> to see what you have already done.
2. Output your reasoning inside <thinking>...</thinking> tags.
   - Analyze what the previous observation means.
   - Decide what information is missing.
3. If you need more data, call a Tool (this happens automatically after your thought).
4. If you have sufficient information, provide the FINAL ANSWER.

If you are ready to answer, start your response with "FINAL ANSWER:".
"""


def _get_tool_call_attr(tool_call: dict[str, Any] | object, key: str) -> object:
    """Read an attribute from a ToolCall regardless of whether it's a dict or model."""
    if isinstance(tool_call, dict):
        return tool_call.get(key)
    return getattr(tool_call, key, None)


def _format_thought_content(thought: Any) -> str:
    """Extract the text content from a thought (model or plain value)."""
    if hasattr(thought, "thought"):
        return str(thought.thought)
    return str(thought)


def _format_tool_call_xml(tool_call: dict[str, Any] | object) -> list[str]:
    """Render a single tool call (action + observation) as XML lines."""
    lines: list[str] = []
    t_name = _get_tool_call_attr(tool_call, "tool_name")
    t_args = _get_tool_call_attr(tool_call, "arguments")
    lines.append(f'    <action tool="{t_name}">{t_args}</action>')

    result = _get_tool_call_attr(tool_call, "result")
    if result:
        lines.append(f"    <observation>{result}</observation>")
    return lines


def format_react_prompt(state: dict[str, Any]) -> str:
    """Format the ReAct loop prompt with current state using XML structure
    optimized for Claude.

    Args:
        state: Agent state dictionary containing iteration tracking,
               thoughts, tool_calls, and the user query.

    Returns:
        Formatted prompt string with XML-structured history.
    """
    history: list[str] = []
    thoughts = state["thoughts"]
    tool_calls = state["tool_calls"]

    for i, thought in enumerate(thoughts):
        iter_log = [f'  <iteration index="{i + 1}">']
        iter_log.append(f"    <thinking>{_format_thought_content(thought)}</thinking>")

        if i < len(tool_calls):
            iter_log.extend(_format_tool_call_xml(tool_calls[i]))

        iter_log.append("  </iteration>")
        history.extend(iter_log)

    history_str = "\n".join(history) if history else "  "

    return REACT_LOOP_PROMPT.format(
        iteration=state["iteration"],
        max_iterations=state["max_iterations"],
        user_query=state["user_query"],
        history=history_str,
    )
