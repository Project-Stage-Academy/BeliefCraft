"""
Shared helpers for post-processing agent tool results.
"""

import json
from typing import Any

LEGACY_RAG_TOOL_NAMES = frozenset(
    {
        "search_knowledge_base",
        "expand_graph_by_ids",
        "get_entity_by_number",
    }
)

CHUNK_TYPE_ALIASES = {
    "algorithm_code": "algorithm",
    "algorythm": "algorithm",
}

ENTITY_TYPE_ALIASES = {
    "algorithm_code": "algorithm",
    "algorythm": "algorithm",
}


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
    """
    Normalize any supported tool result into canonical document dictionaries.

    Canonical shape:
    {
      "id": "...",
      "content": "...",
      "cosine_similarity": 0.93,   # optional
      "metadata": {...}
    }
    """
    return normalize_tool_result(result)["documents"]


def normalize_tool_result(result: Any) -> dict[str, list[dict[str, Any]]]:
    """
    Normalize heterogenous MCP/raw outputs into a canonical result envelope.

    Returns:
        {"documents": [canonical_doc, ...]}
    """
    payload = _unwrap_tool_result(result)
    raw_documents = _extract_raw_documents(payload)

    normalized_documents: list[dict[str, Any]] = []
    for raw_document in raw_documents:
        normalized = normalize_document(raw_document)
        if normalized is not None:
            normalized_documents.append(normalized)

    return {"documents": normalized_documents}


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
    """
    Return canonical metadata.

    Assumes callers pass documents that already went through normalize_document().
    """
    metadata = document.get("metadata")
    if isinstance(metadata, dict):
        return metadata
    return {}


def normalize_document(document: Any) -> dict[str, Any] | None:
    """
    Normalize raw document-like payloads into canonical dict shape.
    """
    raw = _to_dict(document)
    if raw is None:
        return None

    # Native RAG Document shape
    if isinstance(raw.get("id"), str) and isinstance(raw.get("content"), str):
        raw_metadata = raw.get("metadata")
        if isinstance(raw_metadata, dict):
            metadata = dict(raw_metadata)
        else:
            metadata = {
                key: value
                for key, value in raw.items()
                if key not in {"id", "content", "metadata", "cosine_similarity"}
            }
        canonical_metadata = canonicalize_metadata(metadata)
        canonical_metadata.setdefault("chunk_id", raw["id"])
        canonical_metadata.setdefault("id", raw["id"])
        normalized: dict[str, Any] = {
            "id": raw["id"],
            "content": raw["content"],
            "metadata": canonical_metadata,
        }
        cosine_similarity = raw.get("cosine_similarity")
        if isinstance(cosine_similarity, (int, float)):
            normalized["cosine_similarity"] = float(cosine_similarity)
        return normalized

    # Raw chunk JSON shape from parser/fake repository
    if isinstance(raw.get("chunk_id"), str) and isinstance(raw.get("content"), str):
        metadata = {key: value for key, value in raw.items() if key not in {"chunk_id", "content"}}
        canonical_metadata = canonicalize_metadata(metadata)
        canonical_metadata.setdefault("chunk_id", raw["chunk_id"])
        canonical_metadata.setdefault("id", raw["chunk_id"])
        normalized = {
            "id": raw["chunk_id"],
            "content": raw["content"],
            "metadata": canonical_metadata,
        }
        return normalized

    # Metadata-only payloads (useful for defensive compatibility/tests)
    raw_metadata = raw.get("metadata")
    if isinstance(raw_metadata, dict):
        content = raw.get("content")
        normalized_content = content if isinstance(content, str) else ""
        doc_id = raw.get("id") or raw_metadata.get("chunk_id") or raw_metadata.get("id") or ""
        canonical_metadata = canonicalize_metadata(raw_metadata)
        if isinstance(doc_id, str) and doc_id:
            canonical_metadata.setdefault("chunk_id", doc_id)
            canonical_metadata.setdefault("id", doc_id)
        return {
            "id": str(doc_id),
            "content": normalized_content,
            "metadata": canonical_metadata,
        }

    # Loose metadata dictionaries with no explicit metadata wrapper.
    if _looks_like_loose_metadata_payload(raw):
        content = raw.get("content")
        normalized_content = content if isinstance(content, str) else ""
        metadata = {
            key: value for key, value in raw.items() if key not in {"id", "chunk_id", "content"}
        }
        doc_id = raw.get("id") or raw.get("chunk_id") or metadata.get("chunk_id") or ""
        canonical_metadata = canonicalize_metadata(metadata)
        if isinstance(doc_id, str) and doc_id:
            canonical_metadata.setdefault("chunk_id", doc_id)
            canonical_metadata.setdefault("id", doc_id)
        return {
            "id": str(doc_id),
            "content": normalized_content,
            "metadata": canonical_metadata,
        }

    # Already envelope-like or unknown payload -> ignore
    return None


def canonicalize_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    """
    Normalize metadata aliases to reduce coupling with storage schema changes.
    """
    normalized = dict(metadata)

    # Notion/API alias decision: keep section_number canonical and mirror chapter
    chapter = normalized.get("chapter")
    section_number = normalized.get("section_number")
    if chapter is not None and section_number is None:
        normalized["section_number"] = chapter
    elif section_number is not None and chapter is None:
        normalized["chapter"] = section_number

    # Keep both page/page_number accessible
    page = normalized.get("page")
    page_number = normalized.get("page_number")
    if page is not None and page_number is None:
        normalized["page_number"] = page
    elif page_number is not None and page is None:
        normalized["page"] = page_number

    chunk_type = normalized.get("chunk_type")
    if isinstance(chunk_type, str):
        normalized["chunk_type"] = CHUNK_TYPE_ALIASES.get(chunk_type.lower(), chunk_type)

    entity_type = normalized.get("entity_type")
    if isinstance(entity_type, str):
        normalized["entity_type"] = ENTITY_TYPE_ALIASES.get(entity_type.lower(), entity_type)

    raw_type = normalized.get("type")
    if isinstance(raw_type, str):
        normalized["type"] = ENTITY_TYPE_ALIASES.get(raw_type.lower(), raw_type)

    return normalized


def _extract_raw_documents(payload: Any) -> list[Any]:
    """
    Extract document-like objects from typical result envelopes.
    """
    if payload is None:
        return []

    if isinstance(payload, list):
        return payload

    payload_dict = _to_dict(payload)
    if payload_dict is None:
        return [payload]

    for field in ("documents", "results", "expanded"):
        entries = payload_dict.get(field)
        if isinstance(entries, list):
            return entries

    document = payload_dict.get("document")
    if document is not None:
        return [document]

    nested_result = payload_dict.get("result")
    if isinstance(nested_result, list):
        return nested_result
    if nested_result is not None and _is_document_like(nested_result):
        return [nested_result]

    if looks_like_document(payload_dict):
        return [payload_dict]

    if _is_document_like(payload):
        return [payload]

    return []


def _unwrap_tool_result(result: Any) -> Any:
    """
    Unwrap MCP CallToolResult-like objects to their actual payload.
    """
    # FastMCP CallToolResult.data is the best parsed payload when available.
    data = getattr(result, "data", None)
    if data is not None:
        return data

    structured_content = getattr(result, "structured_content", None)
    if structured_content is not None:
        if (
            isinstance(structured_content, dict)
            and "result" in structured_content
            and len(structured_content) == 1
        ):
            return structured_content["result"]
        return structured_content

    # Some libraries expose camelCase fields.
    structured_content = getattr(result, "structuredContent", None)
    if structured_content is not None:
        return structured_content

    # Fallback: try to parse a single textual JSON content block.
    content_blocks = getattr(result, "content", None)
    if isinstance(content_blocks, list) and len(content_blocks) == 1:
        text = getattr(content_blocks[0], "text", None)
        if isinstance(text, str):
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return text

    return result


def _is_document_like(value: Any) -> bool:
    data = _to_dict(value)
    if isinstance(data, dict):
        return looks_like_document(data)
    return False


def _to_dict(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value

    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump()
        if isinstance(dumped, dict):
            return dumped

    # Dataclass-like / plain object fallback
    if hasattr(value, "__dict__"):
        raw = {key: raw_value for key, raw_value in vars(value).items() if not key.startswith("_")}
        if raw:
            return raw

    return None


def _looks_like_loose_metadata_payload(value: dict[str, Any]) -> bool:
    """
    Heuristic for payloads that carry useful metadata but no strict doc wrapper.
    """
    informative_fields = {
        "code_snippet_python",
        "code_snippet_julia",
        "code_language_translated",
        "section_title",
        "subsection_title",
        "chunk_type",
        "type",
        "entity_id",
        "entity_number",
        "page",
        "page_number",
        "title",
    }
    return any(field in value for field in informative_fields)
