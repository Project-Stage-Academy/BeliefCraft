import json
import re
from collections.abc import Mapping
from typing import Any

from langchain_core.messages import AIMessage, ToolMessage


class MessageParser:
    """Consolidates logic for mapping AIMessages to ToolMessages."""

    @staticmethod
    def extract_tool_executions(messages: list[Any]) -> list[dict[str, Any]]:
        """Extract flat list of tool executions."""
        executions = []
        for i, msg in enumerate(messages):
            if not (isinstance(msg, AIMessage) and getattr(msg, "tool_calls", [])):
                continue

            for tc in msg.tool_calls:
                tool_msg = MessageParser._find_tool_message(messages[i + 1 :], tc["id"])
                result, error = MessageParser._extract_payload(tool_msg)

                executions.append(
                    {
                        "tool_name": tc["name"],
                        "arguments": tc["args"],
                        "result": result,
                        "error": error,
                    }
                )
        return executions

    @staticmethod
    def build_iteration_history(
        state: Mapping[str, Any],
        *,
        include_trace_meta: bool = False,
    ) -> list[dict[str, Any]]:
        """Build iteration history from state messages."""
        has_assistant_turns = any(
            MessageParser._is_assistant_message(message) for message in state.get("messages", [])
        )
        if has_assistant_turns:
            return MessageParser._build_iteration_history_from_messages(
                state,
                include_trace_meta=include_trace_meta,
            )
        return MessageParser._build_iteration_history_from_flat_lists(
            state,
            include_trace_meta=include_trace_meta,
        )

    @staticmethod
    def _find_tool_message(sub_messages: list[Any], tool_call_id: str | None) -> ToolMessage | None:
        return next(
            (
                m
                for m in sub_messages
                if isinstance(m, ToolMessage) and m.tool_call_id == tool_call_id
            ),
            None,
        )

    @staticmethod
    def _extract_payload(tool_msg: ToolMessage | None) -> tuple[Any, str | None]:
        if not tool_msg:
            return None, None

        payload = getattr(tool_msg, "artifact", None)
        if payload is None:
            payload = tool_msg.content

        error = str(tool_msg.content) if getattr(tool_msg, "status", None) == "error" else None
        return payload, error

    @staticmethod
    def _format_thought_content(content: Any) -> str:
        if hasattr(content, "thought"):
            content = content.thought
        elif isinstance(content, Mapping):
            content = content.get("thought", content)

        content_str = str(content)
        match = re.search(r"<thinking>(.*?)</thinking>", content_str, flags=re.DOTALL)
        if match:
            return match.group(1).strip()
        return content_str

    @staticmethod
    def _get_tool_call_attr(tool_call: dict[str, Any] | object, key: str) -> object:
        if isinstance(tool_call, dict):
            return tool_call.get(key)
        return getattr(tool_call, key, None)

    @staticmethod
    def _parse_tool_arguments(raw_arguments: Any) -> Any:
        if not isinstance(raw_arguments, str):
            return raw_arguments

        try:
            return json.loads(raw_arguments)
        except json.JSONDecodeError:
            return raw_arguments

    @staticmethod
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

    @staticmethod
    def _extract_message_tool_calls(message: Any) -> list[dict[str, Any]]:
        if isinstance(message, AIMessage):
            raw_tool_calls = getattr(message, "tool_calls", None) or []
            if isinstance(raw_tool_calls, list):
                return MessageParser._normalize_ai_message_tool_calls(raw_tool_calls)
            return []

        if isinstance(message, dict):
            raw_tool_calls = message.get("tool_calls")
            if isinstance(raw_tool_calls, list):
                return [tool_call for tool_call in raw_tool_calls if isinstance(tool_call, dict)]
        return []

    @staticmethod
    def _is_assistant_message(message: Any) -> bool:
        if isinstance(message, AIMessage):
            return True
        return isinstance(message, dict) and message.get("role") == "assistant"

    @staticmethod
    def _parse_tool_observation(content: Any) -> Any:
        if isinstance(content, str):
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                return content
        return content

    @staticmethod
    def _extract_tool_message_observation(message: ToolMessage) -> Any:
        payload = getattr(message, "artifact", None)
        if payload is None:
            payload = message.content

        if getattr(message, "status", None) == "error":
            return {"error": str(message.content)}

        if isinstance(payload, dict) and {"data", "meta"}.issubset(payload):
            return payload if payload else None

        return payload

    @staticmethod
    def _extract_tool_observations_by_id(messages: list[Any]) -> dict[str, Any]:
        observations: dict[str, Any] = {}
        for message in messages:
            if isinstance(message, ToolMessage):
                observations[message.tool_call_id] = (
                    MessageParser._extract_tool_message_observation(message)
                )
                continue

            if isinstance(message, dict) and message.get("role") == "tool":
                tool_call_id = message.get("tool_call_id")
                if tool_call_id:
                    observations[str(tool_call_id)] = MessageParser._parse_tool_observation(
                        message.get("content")
                    )
        return observations

    @staticmethod
    def _build_action_from_recorded_tool_call(
        recorded_tool_call: dict[str, Any] | object,
        *,
        include_trace_meta: bool = False,
    ) -> dict[str, Any]:
        action: dict[str, Any] = {
            "tool": MessageParser._get_tool_call_attr(recorded_tool_call, "tool_name"),
            "arguments": MessageParser._get_tool_call_attr(recorded_tool_call, "arguments"),
        }

        error = MessageParser._get_tool_call_attr(recorded_tool_call, "error")
        if error:
            action["observation"] = {"error": error}
            return action

        result = MessageParser._get_tool_call_attr(recorded_tool_call, "result")
        if result is not None:
            if include_trace_meta:
                trace_meta = MessageParser._get_tool_call_attr(recorded_tool_call, "trace_meta")
                if isinstance(trace_meta, dict) and trace_meta:
                    action["observation"] = {"data": result, "meta": trace_meta}
                    return action
            action["observation"] = result

        return action

    @staticmethod
    def _build_action_from_message_and_recorded_result(
        raw_tool_call: dict[str, Any],
        recorded_tool_call: dict[str, Any] | object | None,
        *,
        include_trace_meta: bool = False,
    ) -> dict[str, Any]:
        function_payload = raw_tool_call.get("function")
        tool_name = None
        tool_arguments: Any = None

        if isinstance(function_payload, dict):
            tool_name = function_payload.get("name")
            tool_arguments = MessageParser._parse_tool_arguments(function_payload.get("arguments"))

        action: dict[str, Any] = {
            "tool": tool_name,
            "arguments": tool_arguments,
        }

        if recorded_tool_call is None:
            return action

        recorded_action = MessageParser._build_action_from_recorded_tool_call(
            recorded_tool_call,
            include_trace_meta=include_trace_meta,
        )
        action["tool"] = recorded_action.get("tool") or action["tool"]
        action["arguments"] = recorded_action.get("arguments") or action["arguments"]

        if "observation" in recorded_action:
            action["observation"] = recorded_action["observation"]

        return action

    @staticmethod
    def _build_iteration_history_from_messages(
        state: Mapping[str, Any],
        *,
        include_trace_meta: bool = False,
    ) -> list[dict[str, Any]]:
        thoughts = state.get("thoughts", [])
        messages = state.get("messages", [])
        assistant_messages = [
            message for message in messages if MessageParser._is_assistant_message(message)
        ]
        tool_observations_by_id = MessageParser._extract_tool_observations_by_id(messages)

        history: list[dict[str, Any]] = []

        for index, assistant_message in enumerate(assistant_messages):
            raw_tool_calls = MessageParser._extract_message_tool_calls(assistant_message)
            actions: list[dict[str, Any]] = []

            for raw_tool_call in raw_tool_calls:
                actions.append(
                    MessageParser._build_action_from_message_and_recorded_result(
                        raw_tool_call,
                        None,
                        include_trace_meta=include_trace_meta,
                    )
                )
                tool_call_id = raw_tool_call.get("id")
                if tool_call_id and "observation" not in actions[-1]:
                    observation = tool_observations_by_id.get(str(tool_call_id))
                    if observation is not None:
                        actions[-1]["observation"] = (
                            observation
                            if include_trace_meta
                            else (
                                observation.get("data", observation)
                                if isinstance(observation, dict)
                                else observation
                            )
                        )

            thought_source = assistant_message.content
            if not str(thought_source).strip() and index < len(thoughts):
                thought_source = thoughts[index]

            history.append(
                {
                    "iteration": index + 1,
                    "thought": MessageParser._format_thought_content(thought_source),
                    "actions": actions,
                }
            )

        return history

    @staticmethod
    def _build_iteration_history_from_flat_lists(
        state: Mapping[str, Any],
        *,
        include_trace_meta: bool = False,
    ) -> list[dict[str, Any]]:
        thoughts = state.get("thoughts", [])
        tool_calls = state.get("tool_calls", [])
        history: list[dict[str, Any]] = []

        for index, thought in enumerate(thoughts):
            actions: list[dict[str, Any]] = []
            if index < len(tool_calls):
                actions.append(
                    MessageParser._build_action_from_recorded_tool_call(
                        tool_calls[index],
                        include_trace_meta=include_trace_meta,
                    )
                )

            history.append(
                {
                    "iteration": index + 1,
                    "thought": MessageParser._format_thought_content(thought),
                    "actions": actions,
                }
            )

        return history
