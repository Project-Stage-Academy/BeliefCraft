"""Service for formatting agent reasoning traces into API responses."""

from typing import Any

from app.models.agent_state import AgentState
from app.services.message_parser import MessageParser


class ReasoningTraceFormatter:
    """Formats agent execution state into structured reasoning trace for API responses."""

    _STANDARD_TOOL_RESULT_KEYS = frozenset({"data", "meta"})

    def format(self, final_state: AgentState) -> list[dict[str, Any]]:
        """
        Format agent state into a reasoning trace with thoughts and actions.

        Args:
            final_state: The final agent state after execution

        Returns:
            List of trace entries, each containing iteration, thought, and optional action
        """
        reasoning_trace: list[dict[str, Any]] = []

        for iteration in MessageParser.build_iteration_history(
            final_state, include_trace_meta=True
        ):
            entry = self._format_entry(iteration)
            reasoning_trace.append(entry)

        return reasoning_trace

    def _format_entry(
        self,
        iteration: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Format a single trace entry with thought and optional action.

        Args:
            iteration: Iteration history entry from build_iteration_history().

        Returns:
            Dictionary with iteration number, thought, and optional action details
        """
        entry: dict[str, Any] = {
            "iteration": iteration["iteration"],
            "thought": iteration["thought"],
        }
        actions = [self._format_action(action) for action in iteration["actions"]]

        if len(actions) == 1:
            entry["action"] = {
                "tool": actions[0]["tool"],
                "arguments": actions[0]["arguments"],
            }
            if "observation" in actions[0]:
                entry["observation"] = actions[0]["observation"]
        elif actions:
            entry["actions"] = actions

        return entry

    @staticmethod
    def _format_action(action: dict[str, Any]) -> dict[str, Any]:
        """Format a single tool action for the public trace."""
        formatted_action: dict[str, Any] = {
            "tool": action.get("tool"),
            "arguments": action.get("arguments"),
        }

        if "observation" not in action:
            return formatted_action

        observation = action["observation"]
        if isinstance(observation, dict):
            if "error" in observation:
                formatted_action["observation"] = f"Error: {observation['error']}"
            elif "documents" in observation:
                formatted_action["observation"] = (
                    f"Received {len(observation['documents'])} documents"
                )
            else:
                count = ReasoningTraceFormatter._count_observation_items(observation)
                formatted_action["observation"] = f"Received {count} data points"
            return formatted_action

        formatted_action["observation"] = "Success"

        return formatted_action

    @staticmethod
    def _count_observation_items(observation: Any) -> int:
        """Count items using trace metadata first and minimal structural fallback second."""
        if isinstance(observation, list):
            return len(observation)

        if not isinstance(observation, dict):
            return 1

        if ReasoningTraceFormatter._is_standard_tool_result(observation):
            return ReasoningTraceFormatter._count_enveloped_payload(observation)

        return ReasoningTraceFormatter._count_payload_items(observation)

    @staticmethod
    def _is_standard_tool_result(observation: dict[str, Any]) -> bool:
        return ReasoningTraceFormatter._STANDARD_TOOL_RESULT_KEYS.issubset(observation)

    @staticmethod
    def _count_enveloped_payload(observation: dict[str, Any]) -> int:
        meta = observation.get("meta")
        trace_count = ReasoningTraceFormatter._extract_meta_int(meta, "trace_count")
        if trace_count is not None:
            return trace_count

        count = ReasoningTraceFormatter._extract_meta_int(meta, "count")
        if count is not None:
            return count

        return ReasoningTraceFormatter._count_payload_items(observation.get("data"))

    @staticmethod
    def _extract_meta_int(meta: Any, key: str) -> int | None:
        if not isinstance(meta, dict):
            return None

        value = meta.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            return value
        return None

    @staticmethod
    def _count_payload_items(payload: Any) -> int:
        if isinstance(payload, list):
            return len(payload)

        if not isinstance(payload, dict):
            return 1

        if "result" in payload and len(payload) == 1:
            return ReasoningTraceFormatter._count_payload_items(payload["result"])

        nested_payloads = [value for value in payload.values() if isinstance(value, (list, dict))]
        if len(nested_payloads) == 1:
            return ReasoningTraceFormatter._count_payload_items(nested_payloads[0])

        return 1
