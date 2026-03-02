"""
Shared helpers for post-processing agent tool results.
"""

from typing import Any

LEGACY_RAG_TOOL_NAMES = frozenset(
    {
        "search_knowledge_base",
        "expand_graph_by_ids",
        "get_entity_by_number",
    }
)


def tool_call_field(tool_call: Any, field_name: str) -> Any:
    """Read a field from a dict-based or model-based tool call."""
    if isinstance(tool_call, dict):
        return tool_call.get(field_name)
    return getattr(tool_call, field_name, None)


def resolve_tool_category(tool_call: Any) -> str | None:
    """
    Resolve tool category from recorded tool-call metadata.

    Falls back to the legacy RAG tool-name list so older persisted states and
    unit tests still behave correctly before category metadata is present.
    """
    category = tool_call_field(tool_call, "category")
    if isinstance(category, str) and category.strip():
        return category.strip()

    tool_name = tool_call_field(tool_call, "tool_name")
    if not isinstance(tool_name, str) or not tool_name.strip():
        return None

    if tool_name in LEGACY_RAG_TOOL_NAMES:
        return "rag"

    return None


def is_rag_tool_call(tool_call: Any) -> bool:
    """Return True when a tool call is known to come from the RAG toolset."""
    return resolve_tool_category(tool_call) == "rag"


def collect_result_documents(result: Any) -> list[dict[str, Any]]:
    """Normalize common tool result payloads into a list of document-like dicts."""
    if isinstance(result, list):
        return [entry for entry in result if isinstance(entry, dict)]

    if not isinstance(result, dict):
        return []

    for field in ("documents", "results", "expanded"):
        entries = result.get(field)
        if isinstance(entries, list):
            return [entry for entry in entries if isinstance(entry, dict)]

    document = result.get("document")
    if isinstance(document, dict):
        return [document]

    if looks_like_document(result):
        return [result]

    return []


def looks_like_document(value: dict[str, Any]) -> bool:
    """Best-effort check for document-like dictionaries returned by RAG tools."""
    candidate_fields = {
        "id",
        "chunk_id",
        "metadata",
        "content",
        "chunk_type",
        "entity_type",
        "number",
        "entity_id",
    }
    return any(field in value for field in candidate_fields)


def extract_metadata(document: dict[str, Any]) -> dict[str, Any]:
    """Return nested metadata if present, otherwise an empty dict."""
    metadata = document.get("metadata")
    return metadata if isinstance(metadata, dict) else {}
