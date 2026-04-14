"""System prompts and formatting utilities for the warehouse advisor ReAct agent."""

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
2. Follow the user's output constraints exactly. Ground the answer in tool observations. \
Include algorithms, formulas, and code snippets when they add meaningful value — \
not just when explicitly requested. Omit them when the answer is purely operational \
(e.g. "how many units are in zone A") and math would add no insight.
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
- Code tool: Execute Python code for calculations, data processing, or simulations.
- Knowledge base tools: Search algorithms and decision-making concepts.
- Skill tools: Load domain-specific diagnostic workflows for complex investigations.

{skill_catalog_section}

Response format:
## Data Findings
Report only what the tools returned:
- What was queried and what was found (specific values, statuses, counts)
- Any anomalies or conflicts in the data
No interpretation here. Facts only. If no tools returned data, state that explicitly.

## Analysis
Interpret the findings through decision-making theory. Answer "what does this mean
and why does it matter":
- Connect data to the relevant algorithm or model (cite textbook if applicable)
- Quantify uncertainty where present (noisy sensors, missing lead times, etc.)
- Include formulas or code only if they concretely support the interpretation
Format ALL math using << $expression$ >> for inline, or:

$$expression$$
>>
for standalone. NEVER write equations as plain text. NEVER use Unicode math
symbols (α, β, γ, ·, ∑) outside of << $...$ >>.
Code: triple backticks with language tag. Omit if prose describes it better.
Do not repeat raw data from Data Findings. Do not jump to recommendations here.

## Recommendations
Write one named block per strategy using this structure:

### <Descriptive title, e.g. "Executive Recommendation" or "Lean Strategy Caution">
**Type**: executive | risk-averse | caution | lean | neutral
<2–4 sentences. State the action, the key numbers, and the tradeoff.>

Rules:
- Always start with an Executive Recommendation block naming the single best option.
- Add 1–3 additional blocks only when meaningful tradeoffs exist.
- Each block must be self-contained.
- If only one course of action exists, write one block only.

Judgment rule: a formula, snippet, or recommendation block earns its place only if
removing it would make the answer meaningfully less clear. If decorative — omit it.
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
