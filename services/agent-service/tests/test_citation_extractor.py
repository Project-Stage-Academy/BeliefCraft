"""
Tests for citation extraction from RAG tool results.
"""

import json
from pathlib import Path

from app.models.agent_state import ToolCall
from app.services.extractors.citation_extractor import CitationExtractor


def _mock_rag_data_path() -> Path:
    repo_root = Path(__file__).resolve().parents[3]
    return (
        repo_root
        / "services"
        / "rag-service"
        / "src"
        / "rag_service"
        / "mock_vector_store_data.json"
    )


def _load_mock_chunks() -> list[dict]:
    with _mock_rag_data_path().open(encoding="utf-8") as f:
        return json.load(f)


def _as_document_shape(raw_chunk: dict) -> dict:
    return {
        "id": raw_chunk["chunk_id"],
        "content": raw_chunk["content"],
        "metadata": {k: v for k, v in raw_chunk.items() if k not in {"chunk_id", "content"}},
    }


def _expected_hierarchy_title(chunk: dict) -> str:
    parts: list[str] = []
    for key in ("part_title", "section_title", "subsection_title", "subsubsection_title"):
        value = chunk.get(key)
        if isinstance(value, str) and value.strip() and value.strip() not in parts:
            parts.append(value.strip())
    return " / ".join(parts)


def test_extract_from_tool_calls_maps_metadata_fields() -> None:
    extractor = CitationExtractor()
    chunks = _load_mock_chunks()
    formula_chunk = next(c for c in chunks if c.get("chunk_type") == "numbered_formula")

    citations = extractor.extract_from_tool_calls(
        [
            {
                "tool_name": "search_knowledge_base",
                "arguments": {"query": "formula"},
                "result": {"documents": [_as_document_shape(formula_chunk)]},
            }
        ]
    )

    assert len(citations) == 1
    citation = citations[0]
    assert citation.chunk_id == formula_chunk["chunk_id"]
    assert citation.page == formula_chunk["page"]
    assert citation.entity_type == "formula"
    assert citation.entity_number == formula_chunk["entity_id"]
    assert citation.title == _expected_hierarchy_title(formula_chunk)


def test_extract_from_tool_calls_supports_flat_result_shape() -> None:
    extractor = CitationExtractor()
    chunks = _load_mock_chunks()
    text_chunk = next(c for c in chunks if c.get("chunk_type") == "text")

    citations = extractor.extract_from_tool_calls(
        [
            {
                "tool_name": "search_knowledge_base",
                "arguments": {"query": "text"},
                "result": {"results": [text_chunk]},
            }
        ]
    )

    assert len(citations) == 1
    citation = citations[0]
    assert citation.chunk_id == text_chunk["chunk_id"]
    assert citation.page == text_chunk["page"]
    assert citation.entity_type == "text"
    assert citation.entity_number is None
    assert citation.title == _expected_hierarchy_title(text_chunk)


def test_extract_from_tool_calls_deduplicates_chunk_ids() -> None:
    extractor = CitationExtractor()
    chunks = _load_mock_chunks()
    table_chunk = next(c for c in chunks if c.get("chunk_type") == "numbered_table")
    document = _as_document_shape(table_chunk)

    tool_calls = [
        {
            "tool_name": "search_knowledge_base",
            "arguments": {"query": "risk table"},
            "result": {"documents": [document]},
        },
        {
            "tool_name": "expand_graph_by_ids",
            "arguments": {"document_ids": [table_chunk["chunk_id"]]},
            "result": {"expanded": [document]},
        },
    ]

    citations = extractor.extract_from_tool_calls(tool_calls)

    assert len(citations) == 1
    assert citations[0].chunk_id == table_chunk["chunk_id"]
    assert citations[0].entity_type == "table"


def test_extract_from_tool_calls_uses_get_entity_arguments_as_fallbacks() -> None:
    extractor = CitationExtractor()

    tool_calls = [
        ToolCall(
            tool_name="get_entity_by_number",
            arguments={"entity_type": "formula", "number": "16.4"},
            result={
                "title": "Bayes Update Rule",
                "content": "P(x|z) = P(z|x)P(x)/P(z)",
                "page": 317,
            },
        ),
        ToolCall(
            tool_name="get_current_observation",
            arguments={},
            result={"warehouse_id": "WH-001"},
        ),
    ]

    citations = extractor.extract_from_tool_calls(tool_calls)

    assert len(citations) == 1
    citation = citations[0]
    assert citation.chunk_id == "formula:16.4"
    assert citation.entity_type == "formula"
    assert citation.entity_number == "16.4"
    assert citation.page == 317
    assert citation.title == "Formula 16.4"


def test_extract_from_tool_calls_uses_tool_category_when_present() -> None:
    extractor = CitationExtractor()
    chunks = _load_mock_chunks()
    formula_chunk = next(c for c in chunks if c.get("chunk_type") == "numbered_formula")

    citations = extractor.extract_from_tool_calls(
        [
            ToolCall(
                tool_name="semantic_lookup_v2",
                category="rag",
                arguments={"query": "bayes"},
                result={"documents": [_as_document_shape(formula_chunk)]},
            )
        ]
    )

    assert len(citations) == 1
    assert citations[0].chunk_id == formula_chunk["chunk_id"]
    assert citations[0].entity_type == "formula"


def test_extract_from_tool_calls_combines_hierarchical_titles() -> None:
    extractor = CitationExtractor()

    citations = extractor.extract_from_tool_calls(
        [
            {
                "tool_name": "search_knowledge_base",
                "arguments": {"query": "hierarchy"},
                "result": {
                    "documents": [
                        {
                            "id": "chunk_x",
                            "content": "text",
                            "metadata": {
                                "chunk_id": "chunk_x",
                                "chunk_type": "text",
                                "part_title": "Part I",
                                "section_title": "Representation",
                                "subsection_title": "Conditional Independence",
                                "subsubsection_title": "D-separation",
                                "page": 42,
                            },
                        }
                    ]
                },
            }
        ]
    )

    assert len(citations) == 1
    assert citations[0].title == "Part I / Representation / Conditional Independence / D-separation"
