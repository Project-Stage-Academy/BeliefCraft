"""Orchestration tools for agent-to-agent communication."""

import json
from typing import Any

from app.tools.base import BaseTool, ToolMetadata
from app.tools.registry import ToolRegistry
from common.logging import get_logger

logger = get_logger(__name__)


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
            return {
                "status": "failed",
                "error": final_state.get("error", "Sub-agent execution failed"),
                "summary": final_state.get("state_summary")
                or "Sub-agent failed before generating a summary.",
                "token_usage": final_state.get("token_usage", {}),
            }

        return {
            "summary": final_state.get("state_summary")
            or "Sub-agent completed but generated no summary.",
            "token_usage": final_state.get("token_usage", {}),
        }


class CallRAGSubAgentTool(BaseTool):
    """Delegates document retrieval and semantic search to a specialized sub-agent."""

    def __init__(self, rag_registry: ToolRegistry) -> None:
        self.rag_registry = rag_registry

        capabilities = [f"{t.metadata.name}" for t in self.rag_registry.list_tools()]
        self._capability_summary = ", ".join(capabilities)

        super().__init__()

    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="call_rag_sub_agent",
            description=(
                "Delegate document retrieval and semantic search to a specialized sub-agent. "
                "This sub-agent finds relevant information in Algorithms for Decision Making book. "
                "The sub-agent has access to the following "
                f"specific RAG tools: [{self._capability_summary}]. Sub-agent will return list of "
                "relevant documents. Don't instruct sub-agent how to perform a task, just give "
                "your query and it will decide by itself how to perform it. Don't talk to "
                "sub-agent like to human. Just write concise query. Optionally you can "
                "tell the maximum number of iterations for agent."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "agent_query": {
                        "type": "string",
                        "description": (
                            "Clear, specific natural language instructions "
                            "outlining exactly what information to find."
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

        from app.services.rag_sub_agent import RAGSubAgent

        sub_agent = RAGSubAgent(tool_registry=self.rag_registry)
        final_state = await sub_agent.run(agent_query=kwargs["agent_query"])

        # Extract all documents from ToolMessages in the history
        all_docs: dict[str, dict[str, Any]] = {}

        for message in final_state.get("messages", []):
            if message.type != "tool":
                continue

            try:
                # Tools return data in a standard envelope
                # TODO: handle types correctly
                content = json.loads(message.content)  # type: ignore
                data = content.get("data")
                if isinstance(data, dict):
                    data = data.get("result")

                # The data can be a single Document (dict) or a list of Documents
                docs_to_process = []
                if isinstance(data, list):
                    docs_to_process = data
                elif isinstance(data, dict) and ("content" in data or "id" in data):
                    # Check if it looks like a Document (has 'content' or 'id')
                    docs_to_process = [data]

                for doc in docs_to_process:
                    if not isinstance(doc, dict):
                        continue
                    doc_id = doc.get("id")
                    if doc_id:
                        all_docs[doc_id] = doc
            except (json.JSONDecodeError, TypeError) as e:
                logger.error(
                    "failed_to_parse_tool_message",
                    message_content=message.content,
                    error=str(e),
                    error_type=type(e).__name__,
                    exc_info=True,
                )

        final_ids = final_state.get("final_chunks_ids")
        if final_ids:
            # Return only relevant documents
            result_docs = [all_docs[doc_id] for doc_id in final_ids if doc_id in all_docs]
        else:
            # subagent failed to specify relevant documents
            # Fallback to return all unique documents found
            result_docs = list(all_docs.values())

        return {
            "documents": result_docs,
            "token_usage": final_state.get("token_usage", {}),
        }
