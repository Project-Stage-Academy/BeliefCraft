try:
    from .agent_eval_runtime import ChunkResolutionIndex, resolve_document_chunk_id
    from .run_evaluation import _collect_documents, _extract_usage_from_response
except ImportError:
    from agent_eval_runtime import ChunkResolutionIndex, resolve_document_chunk_id
    from run_evaluation import _collect_documents, _extract_usage_from_response


def test_collect_documents_handles_nested_envelopes() -> None:
    payload = {
        "result": {
            "documents": [
                {"id": "doc-uuid-1", "metadata": {"chunk_id": "text_a1"}},
                {"chunk_id": "formula_b2", "content": "x"},
            ],
            "expanded": [
                {"id": "algorithm_c3", "content": "algo"},
            ],
        }
    }

    documents = _collect_documents(payload)

    assert [document.get("id") or document.get("chunk_id") for document in documents] == [
        "doc-uuid-1",
        "formula_b2",
        "algorithm_c3",
    ]


def test_extract_usage_from_response_resolves_uuid_with_index() -> None:
    chunk_index = ChunkResolutionIndex(
        known_chunk_ids={"text_1", "text_2", "formula_3"},
        uuid_to_chunk_id={
            "uuid-1": "text_1",
            "uuid-2": "text_2",
            "uuid-3": "formula_3",
        },
    )

    response_payload = {
        "tool_executions": [
            {
                "tool_name": "search_knowledge_base",
                "result": {
                    "documents": [
                        {"id": "uuid-1", "metadata": {}},
                        {"id": "uuid-2", "metadata": {}},
                    ]
                },
                "error": None,
            },
            {
                "tool_name": "expand_graph_by_ids",
                "result": {
                    "documents": [
                        {"id": "uuid-3", "metadata": {}},
                        {"id": "uuid-2", "metadata": {}},
                    ]
                },
                "error": None,
            },
        ],
    }

    usage = _extract_usage_from_response(response_payload, chunk_index)

    assert usage["retrieved_ids"] == ["text_1", "text_2", "formula_3"]
    assert usage["used_rag_tools"] == ["search_knowledge_base", "expand_graph_by_ids"]
    assert usage["per_tool"][0]["chunk_ids"] == ["text_1", "text_2"]
    assert usage["per_tool"][1]["chunk_ids"] == ["formula_3", "text_2"]


def test_extract_usage_from_response_falls_back_to_citations() -> None:
    chunk_index = ChunkResolutionIndex(known_chunk_ids={"text_11", "table_22"})
    response_payload = {
        "status": "completed",
        "citations": [
            {"chunk_id": "text_11"},
            {"chunk_id": "text_11"},
            {"chunk_id": "table_22"},
        ],
    }

    usage = _extract_usage_from_response(response_payload, chunk_index)

    assert usage["retrieved_ids"] == ["text_11", "table_22"]
    assert usage["used_rag_tools"] == []
    assert usage["per_tool"] == []


def test_resolve_document_chunk_id_from_entity_and_chunk_type() -> None:
    chunk_index = ChunkResolutionIndex(
        known_chunk_ids={"text_1"},
        entity_to_chunk_id={("3.1", "numbered_formula"): "text_1"},
    )

    chunk_id, strategy = resolve_document_chunk_id(
        {
            "id": "uuid-x",
            "metadata": {
                "entity_id": "3.1",
                "chunk_type": "numbered_formula",
            },
        },
        chunk_index,
    )

    assert chunk_id == "text_1"
    assert strategy == "entity_chunk_type"
