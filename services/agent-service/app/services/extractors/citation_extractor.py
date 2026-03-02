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


class CitationExtractor:
    """
    Extract citation references from RAG tool results and agent tool calls.
    """

    _CHUNK_TYPE_TO_ENTITY_TYPE = {
        "numbered_formula": "formula",
        "formula": "formula",
        "numbered_table": "table",
        "table": "table",
        "algorithm": "algorithm",
        "captioned_image": "figure",
        "image": "figure",
        "figure": "figure",
        "text": "text",
        "example": "example",
        "exercise": "exercise",
    }

    _ENTITY_PREFIX_BY_TYPE = {
        "formula": "Formula",
        "table": "Table",
        "algorithm": "Algorithm",
        "figure": "Figure",
    }

    def extract_from_rag_results(self, rag_results: dict[str, Any]) -> list[Citation]:
        """
        Extract citations from a single RAG result payload.
        """
        citations = self._extract_citations(rag_results=rag_results, tool_arguments={})
        logger.info("citations_extracted_from_rag_results", count=len(citations))
        return citations

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
        rag_results: Any,
        tool_arguments: dict[str, Any],
    ) -> list[Citation]:
        documents = self._collect_documents(rag_results)
        citations: list[Citation] = []

        for document in documents:
            citation = self._build_citation(document=document, tool_arguments=tool_arguments)
            if citation is not None:
                citations.append(citation)

        return self._deduplicate(citations)

    def _collect_documents(self, rag_results: Any) -> list[dict[str, Any]]:
        return collect_result_documents(rag_results)

    def _build_citation(
        self,
        document: dict[str, Any],
        tool_arguments: dict[str, Any],
    ) -> Citation | None:
        metadata = extract_metadata(document)

        raw_entity_type = self._first_non_empty(
            metadata.get("entity_type"),
            metadata.get("type"),
            metadata.get("chunk_type"),
            document.get("entity_type"),
            document.get("type"),
            document.get("chunk_type"),
            tool_arguments.get("entity_type"),
        )
        entity_type = self._normalize_entity_type(raw_entity_type)

        entity_number = self._first_non_empty(
            metadata.get("entity_number"),
            metadata.get("entity_id"),
            document.get("entity_number"),
            document.get("entity_id"),
            document.get("number"),
            tool_arguments.get("number"),
        )

        if not entity_number:
            link = self._first_non_empty(metadata.get("link"), document.get("link"))
            if link and entity_type in self._ENTITY_PREFIX_BY_TYPE:
                entity_number = f"{self._ENTITY_PREFIX_BY_TYPE[entity_type]} {link}"

        chunk_id = self._first_non_empty(
            document.get("chunk_id"),
            document.get("id"),
            metadata.get("chunk_id"),
            metadata.get("id"),
        )

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

        page = self._extract_page(metadata=metadata, document=document)

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
        title = self._first_non_empty(
            metadata.get("section_title"),
            metadata.get("subsection_title"),
            metadata.get("chapter_title"),
            metadata.get("algorithm_name"),
            metadata.get("title"),
            document.get("section_title"),
            document.get("subsection_title"),
            document.get("chapter_title"),
            document.get("algorithm_name"),
            document.get("title"),
        )
        if title:
            return title

        if entity_type and entity_number:
            prefix = self._ENTITY_PREFIX_BY_TYPE.get(entity_type, entity_type.capitalize())
            return f"{prefix} {entity_number}"

        if entity_number:
            return str(entity_number)

        return "Unknown section"

    @staticmethod
    def _extract_page(metadata: dict[str, Any], document: dict[str, Any]) -> int | None:
        raw_page = (
            metadata.get("page_number")
            or metadata.get("page")
            or document.get("page_number")
            or document.get("page")
        )
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
    def _deduplicate(citations: list[Citation]) -> list[Citation]:
        seen_chunk_ids: set[str] = set()
        deduplicated: list[Citation] = []

        for citation in citations:
            if citation.chunk_id in seen_chunk_ids:
                continue
            seen_chunk_ids.add(citation.chunk_id)
            deduplicated.append(citation)

        return deduplicated
