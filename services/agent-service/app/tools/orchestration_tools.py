"""Orchestration tools for agent-to-agent communication."""

from typing import Any

from app.tools.base import BaseTool, ToolMetadata
from app.tools.registry import ToolRegistry


class CallEnvSubAgentTool(BaseTool):
    """Delegates environment data gathering to the ReWOO sub-agent."""

    def __init__(self, env_registry: ToolRegistry) -> None:
        self.env_registry = env_registry

        capabilities = [f"{t.metadata.name}" for t in self.env_registry.list_tools()]
        self._capability_summary = ", ".join(capabilities)

        super().__init__()

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="call_env_sub_agent",
            description=(
                "Delegate warehouse environment data retrieval to a specialized sub-agent. "
                "This sub-agent executes API calls and returns a concise, factual text summary "
                "of the current reality. "
                "The sub-agent has access to the following "
                f"specific data endpoints: [{self._capability_summary}]. "
                "Provide a highly specific natural language query. "
                "Include exact identifiers (UUIDs, SKUs, POs) and explicitly state what "
                "metrics, statuses, historical trends, or anomalies you need."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "agent_query": {
                        "type": "string",
                        "description": (
                            "Clear, specific natural language instructions "
                            "outlining exactly what data to retrieve and summarize."
                        ),
                    }
                },
                "required": ["agent_query"],
            },
            category="utility",
            skip_cache=True,
        )

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        self._validate_required_params(["agent_query"], kwargs)

        from app.services.env_sub_agent import EnvSubAgent

        sub_agent = EnvSubAgent(tool_registry=self.env_registry)
        final_state = await sub_agent.run(agent_query=kwargs["agent_query"])

        if final_state.get("status") == "failed":
            raise RuntimeError(final_state.get("error", "Sub-agent execution failed"))

        return {
            "summary": final_state.get("state_summary")
            or "Sub-agent completed but generated no summary.",
        }
