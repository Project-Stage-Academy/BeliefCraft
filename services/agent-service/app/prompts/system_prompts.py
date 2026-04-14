"""System prompts and formatting utilities for the warehouse advisor ReAct agent."""

import re
from collections.abc import Mapping
from typing import Any

# Base system prompt (without dynamic skill catalog)
_BASE_WAREHOUSE_ADVISOR_PROMPT = """You are an expert warehouse operations advisor \
powered by the "Algorithms for Decision Making" textbook.

Your role:
- Analyze warehouse state based on observations (potentially noisy/incomplete).
- Apply decision-making algorithms (MDP, POMDP, Bayesian reasoning, inventory control) \
when they are relevant and requested.
- Provide actionable recommendations grounded in tool evidence.

CRITICAL INSTRUCTION:
Before calling any tool or providing a final answer, you MUST analyze the situation \
inside <thinking> tags.

Guidelines:
1. ALWAYS use tools to gather information before reasoning.
2. Follow the user's output constraints exactly. If the user asks for direct evidence \
from tools, ground the answer in tool observations and omit algorithms, formulas, code \
snippets, and recommendations unless the user explicitly requests them.
3. Consider uncertainty (noisy sensors, stochastic lead times).
4. Use knowledge base tools only when the user requests algorithms, theory, formulas, \
or implementation details, or when that information is necessary and does not conflict \
with the user's constraints.
5. If data is conflicting, acknowledge uncertainty.
6. If you call tools at last iteration, you will not see their results and won't be able \
to write any answer to user. So it is better to just answer a question based on info you \
already have, unless it is very critical to call a tool.

Available tool categories:
- Warehouse observation tools: Query inventory, orders, devices, locations.
- Knowledge base tools: Search algorithms and decision-making concepts.
- Skill tools: Load domain-specific diagnostic workflows for complex investigations.

{skill_catalog_section}

Response format:
When you reach a conclusion, provide:
- Task summary
- Analysis grounded in tool outputs
- Relevant algorithm (citation) only when explicitly requested or necessary
- Mathematical formula (LaTeX) only when explicitly requested
- Python code snippet only when explicitly requested
- Actionable recommendations only when requested or clearly helpful and not prohibited
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
- The task requires domain expertise not covered by general reasoning or available tools
- The skill's description matches the user's query or investigation needs
- You need specialized procedures, frameworks, or decision-making workflows

After loading a skill, follow its instructions precisely, including tool call sequences \
and decision points.
"""
    else:
        skill_section = ""

    return _BASE_WAREHOUSE_ADVISOR_PROMPT.format(skill_catalog_section=skill_section)


REACT_LOOP_PROMPT_START = """You are in a ReAct (Reasoning + Acting) loop.

User query:
<query>
{user_query}
</query>

History of previous steps:
<history>"""

REACT_LOOP_PROMPT_END = """</history>

INSTRUCTIONS for this step:
1. Review the <history> to see what you have already done.
2. Output your reasoning inside <thinking>...</thinking> tags.
   - Analyze what the previous observation means.
   - Decide what information is missing.
3. If you need more data, call a Tool (this happens automatically after your thought).
4. If you have sufficient information, provide the FINAL ANSWER.

If you are ready to answer, start your response with "FINAL ANSWER:".

Current iteration: {iteration}/{max_iterations}
"""


def _format_thought_content(content: Any) -> str:
    content_str = str(content)
    match = re.search(r"<thinking>(.*?)</thinking>", content_str, flags=re.DOTALL)
    if match:
        return match.group(1).strip()
    return content_str


def _format_action_xml(action: dict[str, Any]) -> list[str]:
    """Render a single action plus observation as XML lines."""
    lines = [f'    <action tool="{action.get("tool")}">{action.get("arguments")}</action>']
    if "observation" in action:
        lines.append(f"    <observation>{action['observation']}</observation>")
    return lines


def format_react_prompt(state: Mapping[str, Any]) -> list[str]:
    """Format the ReAct loop prompt with current state using XML structure
    optimized for Claude.

    Each iteration is a separate message so that cache checkpoints can be
    added during subsequent prompt processing.

    Args:
        state: Agent state dictionary containing iteration tracking,
               thoughts, tool_calls, and the user query.

    Returns:
        List of formatted prompt strings with XML-structured history.
    """
    from app.services.message_parser import MessageParser

    history: list[str] = [REACT_LOOP_PROMPT_START.format(user_query=state.get("user_query", ""))]
    for iteration in MessageParser.build_iteration_history(state):
        iter_log = [
            f'  <iteration index="{iteration["iteration"]}">',
            f"    <thinking>{iteration['thought']}</thinking>",
        ]

        for action in iteration["actions"]:
            iter_log.extend(_format_action_xml(action))

        iter_log.append("  </iteration>")
        history.append("\n".join(iter_log))

    history.append(
        REACT_LOOP_PROMPT_END.format(
            iteration=state.get("iteration", 1) + 1,  # start from 1
            max_iterations=state.get("max_iterations", 1),
        )
    )
    return history
