"""
Utilities for extracting citations from RAG tool outputs.
"""

from typing import Any

from app.models.responses import Citation
from app.services.extractors.tool_result_utils import (
    collect_result_documents,
    extract_metadata,
    is_rag_tool_call,
    tool_call_field,
)
from common.logging import get_logger

logger = get_logger(__name__)

CanonicalDocument = dict[str, Any]
RagResultPayload = dict[str, Any] | list[CanonicalDocument] | None


class CitationExtractor:
    """
    Extract citation references from RAG tool results and agent tool calls.
    """

    _CHUNK_TYPE_TO_ENTITY_TYPE = {
        "numbered_formula": "formula",
        "numbered_table": "table",
        "algorithm": "algorithm",
        "captioned_image": "image",
        "text": "text",
        "example": "example",
        "exercise": "exercise",
    }

    _ENTITY_PREFIX_BY_TYPE = {
        "formula": "Formula",
        "table": "Table",
        "algorithm": "Algorithm",
        "image": "Image",
    }

    def extract_from_tool_calls(self, tool_calls: list[Any]) -> list[Citation]:
        """
        Extract citations from agent tool call history.

        Supports tool calls represented either as dicts or ToolCall models.
        """
        citations: list[Citation] = []

        for tool_call in tool_calls:
            if not is_rag_tool_call(tool_call):
                continue

            rag_results = tool_call_field(tool_call, "result")
            if not rag_results:
                continue

            tool_arguments_raw = tool_call_field(tool_call, "arguments")
            tool_arguments = tool_arguments_raw if isinstance(tool_arguments_raw, dict) else {}

            citations.extend(
                self._extract_citations(rag_results=rag_results, tool_arguments=tool_arguments)
            )

        deduplicated = self._deduplicate(citations)
        logger.info("citations_extracted_from_tool_calls", count=len(deduplicated))
        return deduplicated

    def _extract_citations(
        self,
        rag_results: RagResultPayload,
        tool_arguments: dict[str, Any],
    ) -> list[Citation]:
        """
        Build citations from a RAG tool payload.

        Supported payload shapes:
        - envelope dicts (e.g. {"documents": [...]}, {"results": [...]}, {"expanded": [...]})
        - plain list of document dicts
        - None
        """
        documents = self._collect_documents(rag_results)
        citations: list[Citation] = []

        for document in documents:
            citation = self._build_citation(document=document, tool_arguments=tool_arguments)
            if citation is not None:
                citations.append(citation)

        return self._deduplicate(citations)

    def _collect_documents(self, rag_results: RagResultPayload) -> list[CanonicalDocument]:
        return collect_result_documents(rag_results)

    def _build_citation(
        self,
        document: dict[str, Any],
        tool_arguments: dict[str, Any],
    ) -> Citation | None:
        metadata = extract_metadata(document)

        # Canonical RAG metadata resolves entity kind via chunk_type.
        # Keep minimal compatibility fallbacks.
        raw_entity_type = self._first_non_empty(
            metadata.get("chunk_type"),
            metadata.get("entity_type"),
            metadata.get("type"),
            tool_arguments.get("entity_type"),
        )
        entity_type = self._normalize_entity_type(raw_entity_type)

        # Canonical RAG metadata uses `entity_id` for numbered entities.
        # For direct-entity tool calls, fall back to the requested `number`.
        entity_number = self._first_non_empty(
            metadata.get("entity_id"),
            tool_arguments.get("number"),
        )

        # Canonical RAG document identity is always provided as `document.id`.
        chunk_id = self._first_non_empty(document.get("id"))

        if not chunk_id and entity_type and entity_number:
            chunk_id = f"{entity_type}:{entity_number}"

        if not chunk_id:
            return None

        title = self._format_title(
            metadata=metadata,
            document=document,
            entity_number=entity_number,
            entity_type=entity_type,
        )

        page = self._extract_page(metadata=metadata)

        return Citation(
            chunk_id=chunk_id,
            title=title,
            page=page,
            entity_type=entity_type,
            entity_number=entity_number,
        )

    def _format_title(
        self,
        metadata: dict[str, Any],
        document: dict[str, Any],
        entity_number: str | None,
        entity_type: str | None,
    ) -> str:
        hierarchy_title = self._join_unique_non_empty(
            metadata.get("part_title"),
            metadata.get("section_title"),
            metadata.get("subsection_title"),
            metadata.get("subsubsection_title"),
        )
        if hierarchy_title:
            return hierarchy_title

        if entity_type and entity_number:
            prefix = self._ENTITY_PREFIX_BY_TYPE.get(entity_type, entity_type.capitalize())
            return f"{prefix} {entity_number}"

        if entity_number:
            return str(entity_number)

        return "Unknown section"

    @staticmethod
    def _extract_page(metadata: dict[str, Any]) -> int | None:
        raw_page = metadata.get("page") or metadata.get("page_number")
        if isinstance(raw_page, int):
            return raw_page if raw_page >= 1 else None
        if isinstance(raw_page, str) and raw_page.isdigit():
            parsed = int(raw_page)
            return parsed if parsed >= 1 else None
        return None

    def _normalize_entity_type(self, raw_entity_type: Any) -> str | None:
        if not isinstance(raw_entity_type, str) or not raw_entity_type.strip():
            return None

        normalized = raw_entity_type.strip().lower()
        if normalized in self._CHUNK_TYPE_TO_ENTITY_TYPE:
            return self._CHUNK_TYPE_TO_ENTITY_TYPE[normalized]
        if normalized.startswith("numbered_"):
            normalized = normalized.replace("numbered_", "", 1)
        return self._CHUNK_TYPE_TO_ENTITY_TYPE.get(normalized, normalized)

    @staticmethod
    def _first_non_empty(*values: Any) -> str | None:
        for value in values:
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    @staticmethod
    def _join_unique_non_empty(*values: Any) -> str | None:
        parts: list[str] = []
        seen: set[str] = set()
        for value in values:
            if not isinstance(value, str):
                continue
            normalized = value.strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            parts.append(normalized)
        if not parts:
            return None
        return " / ".join(parts)

    @staticmethod
    def _deduplicate(citations: list[Citation]) -> list[Citation]:
        # Deduplicate by chunk identity while preserving first-seen order.
        unique_by_chunk_id: dict[str, Citation] = {}
        for citation in citations:
            unique_by_chunk_id.setdefault(citation.chunk_id, citation)
        return list(unique_by_chunk_id.values())
