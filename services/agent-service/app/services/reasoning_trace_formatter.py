"""Service for formatting agent reasoning traces into API responses."""

from typing import Any

from app.models.agent_state import AgentState, ThoughtStep, ToolCall


class ReasoningTraceFormatter:
    """Formats agent execution state into structured reasoning trace for API responses."""

    def format(self, final_state: AgentState) -> list[dict[str, Any]]:
        """
        Format agent state into a reasoning trace with thoughts and actions.

        Args:
            final_state: The final agent state after execution

        Returns:
            List of trace entries, each containing iteration, thought, and optional action
        """
        reasoning_trace = []
        thoughts = final_state["thoughts"]
        tool_calls_list = final_state["tool_calls"]

        for i, thought in enumerate(thoughts):
            entry = self._format_entry(i, thought, tool_calls_list)
            reasoning_trace.append(entry)

        return reasoning_trace

    def _format_entry(
        self,
        index: int,
        thought: ThoughtStep,
        tool_calls_list: list[ToolCall],
    ) -> dict[str, Any]:
        """
        Format a single trace entry with thought and optional action.

        Args:
            index: Zero-based iteration index
            thought: The thought step for this iteration
            tool_calls_list: List of all tool calls from execution

        Returns:
            Dictionary with iteration number, thought, and optional action details
        """
        entry: dict[str, Any] = {
            "iteration": index + 1,
            "thought": thought.thought,
        }

        if index < len(tool_calls_list):
            tool_call = tool_calls_list[index]
            entry["action"] = {
                "tool": tool_call.tool_name,
                "arguments": tool_call.arguments,
                "result": tool_call.result,
            }

        return entry
