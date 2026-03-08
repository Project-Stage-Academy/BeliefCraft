"""System prompts and formatting utilities for the warehouse advisor ReAct agent."""

from typing import Any

# Base system prompt (without dynamic skill catalog)
_BASE_WAREHOUSE_ADVISOR_PROMPT = """You are an expert warehouse operations advisor \
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
- Warehouse observation tools: Query inventory, orders, devices, locations.
- Knowledge base tools: Search algorithms and decision-making concepts.
- Skill tools: Load domain-specific diagnostic workflows for complex investigations.

{skill_catalog_section}

Response format:
When you reach a conclusion, provide:
- Task summary
- Analysis
- Relevant algorithm (citation)
- Mathematical formula (LaTeX)
- Python code snippet
- Actionable recommendations
"""

# Legacy constant for backward compatibility
WAREHOUSE_ADVISOR_SYSTEM_PROMPT = _BASE_WAREHOUSE_ADVISOR_PROMPT.format(skill_catalog_section="")


def get_warehouse_advisor_prompt(skill_catalog: str | None = None) -> str:
    """
    Generate the warehouse advisor system prompt with optional skill catalog.

    Args:
        skill_catalog: XML-formatted skill catalog from SkillStore.get_skill_catalog()
                      If None, prompt will not include skill catalog section.

    Returns:
        Complete system prompt with skill catalog injected (if provided).

    Example:
        ```python
        from app.services.skill_store import SkillStore
        from app.prompts.system_prompts import get_warehouse_advisor_prompt

        store = SkillStore(skills_dir="skills")
        store.scan()
        catalog = store.get_skill_catalog()

        prompt = get_warehouse_advisor_prompt(skill_catalog=catalog)
        ```
    """
    if skill_catalog:
        skill_section = f"""
Available Domain Skills (Tier 1: Discovery):
Use the load_skill tool to activate expert diagnostic workflows when the user's query \
matches a skill's domain. Skills provide step-by-step procedures, tool sequences, and \
decision-making frameworks for complex warehouse operations problems.

<skills_catalog>
{skill_catalog}
</skills_catalog>

When to use skills:
- User asks about specific operational issues (e.g., inventory discrepancies, procurement risks)
- Investigation requires multi-step diagnostic procedure
- Domain expertise beyond general reasoning is needed

After loading a skill, follow its instructions precisely, including tool call sequences \
and decision points.
"""
    else:
        skill_section = ""

    return _BASE_WAREHOUSE_ADVISOR_PROMPT.format(skill_catalog_section=skill_section)


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
