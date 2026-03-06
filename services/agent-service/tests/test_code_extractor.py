"""
Tests for code snippet extraction and enrichment.
"""

import json
from pathlib import Path

import pytest
from app.models.agent_state import ToolCall
from app.services.extractors.code_extractor import CodeExtractor


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
    with _mock_rag_data_path().open(encoding="utf-8") as file:
        return json.load(file)


def _as_document_shape(raw_chunk: dict) -> dict:
    return {
        "id": raw_chunk["chunk_id"],
        "content": raw_chunk["content"],
        "metadata": {
            key: value for key, value in raw_chunk.items() if key not in {"chunk_id", "content"}
        },
    }


def test_extract_from_text_returns_empty_for_empty_input() -> None:
    extractor = CodeExtractor()
    assert extractor.extract_from_text("") == []


def test_extract_from_text_extracts_python_and_detects_dependencies() -> None:
    extractor = CodeExtractor()
    text = "```python\nimport math\nfrom numpy import array\nx = array([math.sqrt(4)])\n```"

    snippets = extractor.extract_from_text(text)

    assert len(snippets) == 1
    snippet = snippets[0]
    assert snippet.language == "python"
    assert snippet.validated is True
    assert snippet.dependencies == ["math", "numpy"]


def test_extract_from_text_infers_python_without_language_hint() -> None:
    extractor = CodeExtractor()
    text = (
        "```\n"
        "def reorder_point(daily_demand, lead_time):\n"
        "    return daily_demand * lead_time\n"
        "```"
    )

    snippets = extractor.extract_from_text(text)

    assert len(snippets) == 1
    assert snippets[0].language == "python"
    assert snippets[0].validated is True


def test_extract_from_text_infers_julia_pattern() -> None:
    extractor = CodeExtractor()
    text = "```\nfunction POLICY(x)\n    return x\nend\n```"

    snippets = extractor.extract_from_text(text)

    assert len(snippets) == 1
    assert snippets[0].language == "julia"
    assert snippets[0].validated is False


def test_extract_from_text_downgrades_invalid_python_to_text() -> None:
    extractor = CodeExtractor()
    text = "```python\ndef broken(:\n    pass\n```"

    snippets = extractor.extract_from_text(text)

    assert len(snippets) == 1
    assert snippets[0].language == "text"
    assert snippets[0].validated is False
    assert snippets[0].dependencies == []


def test_extract_from_document_reads_algorithm_content_and_description() -> None:
    extractor = CodeExtractor()
    document = {
        "content": "import math\nreorder_point = math.ceil(12.2)",
        "metadata": {
            "section_title": "Safety Stock",
            "chunk_type": "algorithm",
        },
    }

    snippets = extractor.extract_from_document(document)

    assert len(snippets) == 1
    snippet = snippets[0]
    assert snippet.language == "python"
    assert snippet.description == "Safety Stock"
    assert snippet.validated is True
    assert snippet.dependencies == ["math"]


def test_extract_from_document_uses_declared_metadata_dependencies() -> None:
    extractor = CodeExtractor()
    document = {
        "content": "import math\nx = math.sqrt(4)",
        "metadata": {
            "section_title": "Policy",
            "chunk_type": "algorithm",
            "dependencies": ["numpy", "scipy"],
        },
    }

    snippets = extractor.extract_from_document(document)

    assert len(snippets) == 1
    assert snippets[0].language == "python"
    assert snippets[0].validated is True
    assert snippets[0].dependencies == ["numpy", "scipy"]


def test_extract_from_document_reads_algorithm_chunk_content_from_mock_data() -> None:
    extractor = CodeExtractor()
    chunks = _load_mock_chunks()
    algorithm_chunk = next(c for c in chunks if c.get("chunk_type") == "algorithm")

    snippets = extractor.extract_from_document(algorithm_chunk)

    assert len(snippets) == 1
    assert snippets[0].code == algorithm_chunk["content"]
    assert snippets[0].description == algorithm_chunk["section_title"]
    assert snippets[0].language == "text"
    assert snippets[0].validated is False


def test_extract_from_document_applies_section_description_to_fenced_content() -> None:
    extractor = CodeExtractor()
    document = {
        "section_title": "Demand Forecasting",
        "content": (
            "Use this implementation:\n"
            "```python\n"
            "import pandas as pd\n"
            "series = pd.Series([1, 2, 3])\n"
            "```\n"
        ),
    }

    snippets = extractor.extract_from_document(document)

    assert len(snippets) == 1
    assert snippets[0].description == "Demand Forecasting"
    assert snippets[0].language == "python"
    assert snippets[0].dependencies == ["pandas"]


def test_extract_from_document_deduplicates_same_code_from_fields_and_fences() -> None:
    extractor = CodeExtractor()
    document = {
        "section_title": "Duplication Case",
        "content": (
            "```python\nimport math\nx = math.sqrt(9)\n```\n"
            "Repeated:\n"
            "```python\nimport math\nx = math.sqrt(9)\n```"
        ),
    }

    snippets = extractor.extract_from_document(document)

    assert len(snippets) == 1
    assert snippets[0].language == "python"


@pytest.mark.parametrize(
    "result_payload",
    [
        {"documents": [{"chunk_type": "algorithm", "content": "import math\nx = math.sqrt(4)"}]},
        {"results": [{"chunk_type": "algorithm", "content": "import math\nx = math.sqrt(4)"}]},
        {"expanded": [{"chunk_type": "algorithm", "content": "import math\nx = math.sqrt(4)"}]},
        {"document": {"chunk_type": "algorithm", "content": "import math\nx = math.sqrt(4)"}},
        {
            "chunk_id": "chunk_x",
            "chunk_type": "algorithm",
            "content": "import math\nx = math.sqrt(4)",
        },
        [{"chunk_type": "algorithm", "content": "import math\nx = math.sqrt(4)"}],
    ],
)
def test_extract_from_answer_and_tool_calls_supports_result_shapes(result_payload: object) -> None:
    extractor = CodeExtractor()
    tool_calls = [
        {
            "tool_name": "search_knowledge_base",
            "arguments": {"query": "safety stock"},
            "result": result_payload,
        }
    ]

    snippets = extractor.extract_from_answer_and_tool_calls(
        final_answer="",
        tool_calls=tool_calls,
    )

    assert len(snippets) == 1
    assert snippets[0].language == "python"
    assert snippets[0].validated is True


def test_extract_from_answer_and_tool_calls_ignores_non_rag_tools() -> None:
    extractor = CodeExtractor()
    tool_calls = [
        {
            "tool_name": "get_current_observation",
            "arguments": {},
            "result": {
                "documents": [
                    {"chunk_type": "algorithm", "content": "import math\nx = math.sqrt(4)"}
                ]
            },
        }
    ]

    snippets = extractor.extract_from_answer_and_tool_calls(
        final_answer="",
        tool_calls=tool_calls,
    )

    assert snippets == []


def test_extract_from_answer_and_tool_calls_accepts_toolcall_models() -> None:
    extractor = CodeExtractor()
    tool_calls = [
        ToolCall(
            tool_name="search_knowledge_base",
            arguments={"query": "q-learning"},
            result={
                "documents": [
                    {"chunk_type": "algorithm", "content": "import random\nx = random.random()"}
                ]
            },
        )
    ]

    snippets = extractor.extract_from_answer_and_tool_calls(
        final_answer="",
        tool_calls=tool_calls,
    )

    assert len(snippets) == 1
    assert snippets[0].language == "python"
    assert snippets[0].dependencies == ["random"]


def test_extract_from_answer_and_tool_calls_uses_tool_category_when_present() -> None:
    extractor = CodeExtractor()
    tool_calls = [
        ToolCall(
            tool_name="semantic_lookup_v2",
            category="rag",
            arguments={"query": "policy iteration"},
            result={
                "documents": [
                    {"chunk_type": "algorithm", "content": "import math\nx = math.sqrt(25)"}
                ]
            },
        )
    ]

    snippets = extractor.extract_from_answer_and_tool_calls(
        final_answer="",
        tool_calls=tool_calls,
    )

    assert len(snippets) == 1
    assert snippets[0].language == "python"
    assert snippets[0].dependencies == ["math"]


def test_extract_from_answer_and_tool_calls_deduplicates_across_sources() -> None:
    extractor = CodeExtractor()
    final_answer = "```python\nimport math\nx = math.sqrt(16)\n```"
    tool_calls = [
        {
            "tool_name": "search_knowledge_base",
            "arguments": {"query": "sqrt"},
            "result": {
                "documents": [
                    {"chunk_type": "algorithm", "content": "import math\nx = math.sqrt(16)"}
                ]
            },
        }
    ]

    snippets = extractor.extract_from_answer_and_tool_calls(
        final_answer=final_answer,
        tool_calls=tool_calls,
    )

    assert len(snippets) == 1
    assert snippets[0].language == "python"


def test_extract_from_document_supports_nested_document_shape_from_mock_chunk() -> None:
    extractor = CodeExtractor()
    chunks = _load_mock_chunks()
    algorithm_chunk = next(c for c in chunks if c.get("chunk_type") == "algorithm")
    nested_document = _as_document_shape(algorithm_chunk)

    snippets = extractor.extract_from_document(nested_document)

    assert len(snippets) == 1
    assert snippets[0].description == algorithm_chunk["section_title"]
    assert snippets[0].code == algorithm_chunk["content"]
