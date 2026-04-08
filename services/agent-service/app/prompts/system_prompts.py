"""System prompts and formatting utilities for the warehouse advisor ReAct agent."""

import json
import re
from collections.abc import Mapping
from typing import Any

from langchain_core.messages import AIMessage, ToolMessage

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


def _format_thought_content(content: Any) -> str:
    content_str = str(content)
    match = re.search(r"<thinking>(.*?)</thinking>", content_str, flags=re.DOTALL)
    if match:
        return match.group(1).strip()
    return content_str


def _parse_tool_arguments(raw_arguments: Any) -> Any:
    """Parse tool arguments for display while preserving non-JSON inputs."""
    if not isinstance(raw_arguments, str):
        return raw_arguments

    try:
        return json.loads(raw_arguments)
    except json.JSONDecodeError:
        return raw_arguments


def _normalize_ai_message_tool_calls(tool_calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized_calls: list[dict[str, Any]] = []
    for tool_call in tool_calls:
        if not isinstance(tool_call, dict):
            continue

        if "function" in tool_call:
            normalized_calls.append(tool_call)
            continue

        normalized_calls.append(
            {
                "id": tool_call.get("id"),
                "type": "function",
                "function": {
                    "name": tool_call.get("name"),
                    "arguments": json.dumps(tool_call.get("args", {})),
                },
            }
        )
    return normalized_calls


def _extract_message_tool_calls(message: Any) -> list[dict[str, Any]]:
    """Return tool calls declared on an assistant message."""
    if isinstance(message, AIMessage):
        raw_tool_calls = getattr(message, "tool_calls", None) or []
        if isinstance(raw_tool_calls, list):
            return _normalize_ai_message_tool_calls(raw_tool_calls)
        return []

    if isinstance(message, dict):
        raw_tool_calls = message.get("tool_calls")
        if isinstance(raw_tool_calls, list):
            return [tool_call for tool_call in raw_tool_calls if isinstance(tool_call, dict)]
    return []


def _is_assistant_message(message: Any) -> bool:
    if isinstance(message, AIMessage):
        return True
    return isinstance(message, dict) and message.get("role") == "assistant"


def _parse_tool_observation(content: Any) -> Any:
    if isinstance(content, str):
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return content
    return content


def _extract_tool_message_observation(message: ToolMessage) -> Any:
    payload = getattr(message, "artifact", None)
    if payload is None:
        payload = message.content

    if getattr(message, "status", None) == "error":
        return {"error": str(message.content)}

    if isinstance(payload, dict) and {"data", "meta"}.issubset(payload):
        return payload.get("data")

    return payload


def _extract_tool_observations_by_id(messages: list[Any]) -> dict[str, Any]:
    observations: dict[str, Any] = {}
    for message in messages:
        if isinstance(message, ToolMessage):
            observations[message.tool_call_id] = _extract_tool_message_observation(message)
            continue

        if isinstance(message, dict) and message.get("role") == "tool":
            tool_call_id = message.get("tool_call_id")
            if tool_call_id:
                observations[str(tool_call_id)] = _parse_tool_observation(message.get("content"))
    return observations


def _build_action_from_recorded_tool_call(
    recorded_tool_call: dict[str, Any] | object,
    *,
    include_trace_meta: bool = False,
) -> dict[str, Any]:
    """Build a prompt/reasoning action from a recorded ToolCall."""
    action: dict[str, Any] = {
        "tool": _get_tool_call_attr(recorded_tool_call, "tool_name"),
        "arguments": _get_tool_call_attr(recorded_tool_call, "arguments"),
    }

    error = _get_tool_call_attr(recorded_tool_call, "error")
    if error:
        action["observation"] = {"error": error}
        return action

    result = _get_tool_call_attr(recorded_tool_call, "result")
    if result is not None:
        if include_trace_meta:
            trace_meta = _get_tool_call_attr(recorded_tool_call, "trace_meta")
            if isinstance(trace_meta, dict) and trace_meta:
                action["observation"] = {"data": result, "meta": trace_meta}
                return action
        action["observation"] = result

    return action


def _build_action_from_message_and_recorded_result(
    raw_tool_call: dict[str, Any],
    recorded_tool_call: dict[str, Any] | object | None,
    *,
    include_trace_meta: bool = False,
) -> dict[str, Any]:
    """Build a prompt/reasoning action for one assistant-declared tool call."""
    function_payload = raw_tool_call.get("function")
    tool_name = None
    tool_arguments: Any = None

    if isinstance(function_payload, dict):
        tool_name = function_payload.get("name")
        tool_arguments = _parse_tool_arguments(function_payload.get("arguments"))

    action: dict[str, Any] = {
        "tool": tool_name,
        "arguments": tool_arguments,
    }

    if recorded_tool_call is None:
        return action

    recorded_action = _build_action_from_recorded_tool_call(
        recorded_tool_call,
        include_trace_meta=include_trace_meta,
    )
    action["tool"] = recorded_action.get("tool") or action["tool"]
    action["arguments"] = recorded_action.get("arguments") or action["arguments"]

    if "observation" in recorded_action:
        action["observation"] = recorded_action["observation"]

    return action


def _build_iteration_history_from_messages(
    state: Mapping[str, Any],
    *,
    include_trace_meta: bool = False,
) -> list[dict[str, Any]]:
    """Build iteration history using assistant-turn boundaries from raw messages."""
    thoughts = state.get("thoughts", [])
    recorded_tool_calls = state.get("tool_calls", [])
    messages = state.get("messages", [])
    assistant_messages = [message for message in messages if _is_assistant_message(message)]
    tool_observations_by_id = _extract_tool_observations_by_id(messages)

    history: list[dict[str, Any]] = []
    tool_call_cursor = 0

    for index, assistant_message in enumerate(assistant_messages):
        raw_tool_calls = _extract_message_tool_calls(assistant_message)
        actions: list[dict[str, Any]] = []

        for offset, raw_tool_call in enumerate(raw_tool_calls):
            recorded_tool_call = None
            recorded_index = tool_call_cursor + offset
            if recorded_index < len(recorded_tool_calls):
                recorded_tool_call = recorded_tool_calls[recorded_index]
            actions.append(
                _build_action_from_message_and_recorded_result(
                    raw_tool_call,
                    recorded_tool_call,
                    include_trace_meta=include_trace_meta,
                )
            )
            tool_call_id = raw_tool_call.get("id")
            if tool_call_id and "observation" not in actions[-1]:
                observation = tool_observations_by_id.get(str(tool_call_id))
                if observation is not None:
                    actions[-1]["observation"] = observation

        history.append(
            {
                "iteration": index + 1,
                "thought": _format_thought_content(
                    thoughts[index] if index < len(thoughts) else assistant_message.content
                ),
                "actions": actions,
            }
        )
        tool_call_cursor += len(raw_tool_calls)

    return history


def _build_iteration_history_from_flat_lists(
    state: Mapping[str, Any],
    *,
    include_trace_meta: bool = False,
) -> list[dict[str, Any]]:
    """Fallback history builder for tests or older states without raw messages."""
    thoughts = state.get("thoughts", [])
    tool_calls = state.get("tool_calls", [])
    history: list[dict[str, Any]] = []

    for index, thought in enumerate(thoughts):
        actions: list[dict[str, Any]] = []
        if index < len(tool_calls):
            actions.append(
                _build_action_from_recorded_tool_call(
                    tool_calls[index],
                    include_trace_meta=include_trace_meta,
                )
            )

        history.append(
            {
                "iteration": index + 1,
                "thought": _format_thought_content(thought),
                "actions": actions,
            }
        )

    return history


def build_iteration_history(
    state: Mapping[str, Any],
    *,
    include_trace_meta: bool = False,
) -> list[dict[str, Any]]:
    """Return iteration history with exact assistant-turn to tool-call grouping."""
    has_assistant_turns = any(
        _is_assistant_message(message) for message in state.get("messages", [])
    )
    if has_assistant_turns:
        return _build_iteration_history_from_messages(
            state,
            include_trace_meta=include_trace_meta,
        )
    return _build_iteration_history_from_flat_lists(
        state,
        include_trace_meta=include_trace_meta,
    )


def _format_action_xml(action: dict[str, Any]) -> list[str]:
    """Render a single action plus observation as XML lines."""
    lines = [f'    <action tool="{action.get("tool")}">{action.get("arguments")}</action>']
    if "observation" in action:
        lines.append(f'    <observation>{action["observation"]}</observation>')
    return lines


def format_react_prompt(state: Mapping[str, Any]) -> str:
    """Format the ReAct loop prompt with current state using XML structure
    optimized for Claude.

    Args:
        state: Agent state dictionary containing iteration tracking,
               thoughts, tool_calls, and the user query.

    Returns:
        Formatted prompt string with XML-structured history.
    """
    history: list[str] = []
    for iteration in build_iteration_history(state):
        iter_log = [f'  <iteration index="{iteration["iteration"]}">']
        iter_log.append(f'    <thinking>{iteration["thought"]}</thinking>')

        for action in iteration["actions"]:
            iter_log.extend(_format_action_xml(action))

        iter_log.append("  </iteration>")
        history.extend(iter_log)

    history_str = "\n".join(history) if history else "  "

    return REACT_LOOP_PROMPT.format(
        iteration=state.get("iteration", 1),
        max_iterations=state.get("max_iterations", 1),
        user_query=state.get("user_query", ""),
        history=history_str,
    )
