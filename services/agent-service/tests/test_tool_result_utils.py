from dataclasses import dataclass
from typing import Any

from app.services.extractors.tool_result_utils import (
    collect_result_documents,
    is_rag_tool_call,
)


@dataclass
class _FakeDocument:
    id: str
    content: str
    cosine_similarity: float
    metadata: dict[str, Any]

    def model_dump(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content,
            "cosine_similarity": self.cosine_similarity,
            "metadata": self.metadata,
        }


@dataclass
class _FakeCallToolResult:
    data: Any = None
    structured_content: Any = None
    content: list[Any] | None = None


def test_collect_result_documents_normalizes_raw_chunk_and_aliases() -> None:
    raw_chunk = {
        "chunk_id": "chunk_001",
        "content": "algorithm body",
        "chunk_type": "algorithm_code",
        "section_number": "2",
        "page": 23,
    }

    documents = collect_result_documents({"results": [raw_chunk]})

    assert len(documents) == 1
    document = documents[0]
    metadata = document["metadata"]

    assert document["id"] == "chunk_001"
    assert metadata["chunk_type"] == "algorithm"
    assert metadata["section_number"] == "2"
    assert metadata["chapter"] == "2"
    assert metadata["page"] == 23
    assert metadata["page_number"] == 23
    assert metadata["chunk_id"] == "chunk_001"


def test_collect_result_documents_unwraps_call_tool_result_data() -> None:
    tool_result = _FakeCallToolResult(
        data=[
            _FakeDocument(
                id="chunk_002",
                content="content",
                cosine_similarity=0.91,
                metadata={
                    "chunk_type": "algorithm_code",
                    "entity_type": "algorithm_code",
                    "chapter": "3",
                },
            )
        ]
    )

    documents = collect_result_documents(tool_result)

    assert len(documents) == 1
    document = documents[0]
    metadata = document["metadata"]

    assert document["id"] == "chunk_002"
    assert document["cosine_similarity"] == 0.91
    assert metadata["chunk_type"] == "algorithm"
    assert metadata["entity_type"] == "algorithm"
    assert metadata["chapter"] == "3"
    assert metadata["section_number"] == "3"


def test_collect_result_documents_unwraps_structured_content_result_wrapper() -> None:
    tool_result = _FakeCallToolResult(
        structured_content={
            "result": {
                "documents": [
                    {
                        "id": "chunk_003",
                        "content": "text",
                        "metadata": {"chunk_type": "text"},
                    }
                ]
            }
        }
    )

    documents = collect_result_documents(tool_result)

    assert len(documents) == 1
    assert documents[0]["id"] == "chunk_003"
    assert documents[0]["metadata"]["chunk_type"] == "text"


def test_collect_result_documents_handles_loose_metadata_payload() -> None:
    documents = collect_result_documents(
        {"documents": [{"code_snippet_python": "import math\nx = math.sqrt(4)"}]}
    )

    assert len(documents) == 1
    assert documents[0]["id"] == ""
    assert documents[0]["content"] == ""
    assert "code_snippet_python" in documents[0]["metadata"]


def test_collect_result_documents_ignores_non_document_payloads() -> None:
    documents = collect_result_documents({"documents": [{"unexpected": "shape"}]})
    assert documents == []


def test_collect_result_documents_ignores_string_utility_payload() -> None:
    source_fragment = "def helper():\n    return 1"

    documents = collect_result_documents(source_fragment)

    assert documents == []


def test_get_related_code_definitions_not_legacy_rag_by_name_fallback() -> None:
    # Keep extractor fallback scoped to legacy document-envelope RAG tools only.
    tool_call = {"tool_name": "get_related_code_definitions"}

    assert is_rag_tool_call(tool_call) is False
