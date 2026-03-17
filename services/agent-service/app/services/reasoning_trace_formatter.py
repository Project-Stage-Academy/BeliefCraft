"""Service for formatting agent reasoning traces into API responses."""

from typing import Any

from app.models.agent_state import AgentState
from app.prompts.system_prompts import build_iteration_history


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
        reasoning_trace: list[dict[str, Any]] = []

        for iteration in build_iteration_history(final_state):
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
                formatted_action["observation"] = f"Received {len(observation)} data points"
            return formatted_action

        formatted_action["observation"] = "Success"

        return formatted_action
