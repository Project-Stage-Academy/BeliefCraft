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
        messages = state.get("messages", [])
        history = []
        iteration_index = 1

        for i, msg in enumerate(messages):
            if not (isinstance(msg, AIMessage) and (msg.content or getattr(msg, "tool_calls", []))):
                continue

            actions = []
            for tc in getattr(msg, "tool_calls", []):
                tool_msg = MessageParser._find_tool_message(messages[i + 1 :], tc["id"])
                result, error = MessageParser._extract_payload(tool_msg)

                action = {
                    "tool": tc["name"],
                    "arguments": tc["args"],
                }

                if tool_msg:
                    if error is not None:
                        action["observation"] = {"error": error}
                    else:
                        if include_trace_meta and isinstance(result, dict):
                            action["observation"] = result
                        else:
                            action["observation"] = (
                                result.get("data", result) if isinstance(result, dict) else result
                            )

                actions.append(action)

            if str(msg.content).strip() or actions:
                history.append(
                    {
                        "iteration": iteration_index,
                        "thought": MessageParser._format_thought_content(msg.content),
                        "actions": actions,
                    }
                )
                iteration_index += 1

        return history

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
        content_str = str(content)
        match = re.search(r"<thinking>(.*?)</thinking>", content_str, flags=re.DOTALL)
        if match:
            return match.group(1).strip()
        return content_str
