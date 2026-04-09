import json
from pathlib import Path

from rag_scripts import concept_mapping as cm
from rag_scripts import concept_tags_generator as ctg


def test_concept_tags_normalize_and_deduplicate() -> None:
    raw_tags = [
        "belief update",
        "Belief-Update",
        "BELIEF_UPDATE",
        "optimization",
        "OPT",
        "??",
    ]

    deduped = ctg.deduplicate_tags(raw_tags)

    assert "BELIEF_UPDATE" in deduped
    assert "OPTIMIZATION" in deduped
    assert "OPT" not in deduped
    assert "" not in deduped


def test_concept_tags_parse_json_response_with_markdown_fence() -> None:
    payload = """```json
{"tags": ["A", "B"]}
```"""

    parsed = ctg.parse_json_response(payload)

    assert parsed == {"tags": ["A", "B"]}


def test_concept_tags_generate_tags_for_batch_filters_invalid(monkeypatch) -> None:
    def fake_call_bedrock(client, system_prompt: str, user_prompt: str) -> str:  # noqa: ARG001
        return json.dumps({"tags": ["belief update", "ok_tag", "??"]})

    monkeypatch.setattr(ctg, "call_bedrock", fake_call_bedrock)

    tags = ctg.generate_tags_for_batch(client=object(), batch=[{"content": "test"}])

    assert tags == ["BELIEF_UPDATE", "OK_TAG"]


def test_concept_mapping_load_jsonl_handles_invalid_lines(tmp_path: Path) -> None:
    path = tmp_path / "data.jsonl"
    path.write_text(
        "\n".join(
            [
                json.dumps({"chunk_id": "c1", "bc_concepts": ["A"]}),
                "not-json",
                json.dumps({"chunk_id": "c2", "bc_db_tables": ["orders"]}),
                json.dumps({"missing_id": "x"}),
            ]
        ),
        encoding="utf-8",
    )

    loaded = cm.load_jsonl(path)

    assert set(loaded.keys()) == {"c1", "c2"}


def test_concept_mapping_create_batches_respects_token_budget() -> None:
    class DeterministicRng:
        def shuffle(self, sequence) -> None:
            # Keep order stable for deterministic unit tests.
            return None

    items = [
        {"chunk_id": "c1", "content": "a" * 200},
        {"chunk_id": "c2", "content": "b" * 200},
        {"chunk_id": "c3", "content": "c" * 200},
    ]

    batches = cm.create_batches(items, max_tokens=130, rng=DeterministicRng())

    assert len(batches) == 3
    assert sorted(x["chunk_id"] for b in batches for x in b) == ["c1", "c2", "c3"]


def test_concept_mapping_tag_concepts_batch_filters_unknown_tags(monkeypatch) -> None:
    def fake_call_bedrock(client, system_prompt: str, user_prompt: str) -> str:  # noqa: ARG001
        return json.dumps(
            {
                "results": [
                    {"chunk_id": "c1", "bc_concepts": ["KNOWN", "UNKNOWN"]},
                    {"chunk_id": "c2", "bc_concepts": []},
                    {"bc_concepts": ["KNOWN"]},
                ]
            }
        )

    monkeypatch.setattr(cm, "call_bedrock", fake_call_bedrock)

    result = cm.tag_concepts_batch(
        client=object(),
        batch=[{"chunk_id": "c1", "content": "a"}, {"chunk_id": "c2", "content": "b"}],
        concept_tags=["KNOWN"],
    )

    assert result == [
        {"chunk_id": "c1", "bc_concepts": ["KNOWN"]},
        {"chunk_id": "c2", "bc_concepts": []},
    ]


def test_concept_mapping_tag_tables_batch_filters_unknown_tables(monkeypatch) -> None:
    def fake_call_bedrock(client, system_prompt: str, user_prompt: str) -> str:  # noqa: ARG001
        return json.dumps(
            {
                "results": [
                    {"chunk_id": "c1", "bc_db_tables": ["orders", "not_a_table"]},
                    {"chunk_id": "c2", "bc_db_tables": []},
                    {"bc_db_tables": ["orders"]},
                ]
            }
        )

    monkeypatch.setattr(cm, "call_bedrock", fake_call_bedrock)

    result = cm.tag_tables_batch(
        client=object(),
        batch=[{"chunk_id": "c1", "content": "a"}, {"chunk_id": "c2", "content": "b"}],
    )

    assert result == [
        {"chunk_id": "c1", "bc_db_tables": ["orders"]},
        {"chunk_id": "c2", "bc_db_tables": []},
    ]


def test_concept_mapping_phase3_merge_fills_missing_tags(tmp_path: Path) -> None:
    chunks = [
        {"chunk_id": "c1", "content": "one"},
        {"chunk_id": "c2", "content": "two"},
    ]
    concepts_path = tmp_path / "concepts.jsonl"
    tables_path = tmp_path / "tables.jsonl"
    output_path = tmp_path / "out.json"

    concepts_path.write_text(
        json.dumps({"chunk_id": "c1", "bc_concepts": ["TAG_1"]}) + "\n",
        encoding="utf-8",
    )
    tables_path.write_text(
        json.dumps({"chunk_id": "c2", "bc_db_tables": ["orders"]}) + "\n",
        encoding="utf-8",
    )

    cm.run_phase3_merge(chunks, concepts_path, tables_path, output_path)

    merged = json.loads(output_path.read_text(encoding="utf-8"))
    assert merged == [
        {
            "chunk_id": "c1",
            "content": "one",
            "bc_concepts": ["TAG_1"],
            "bc_db_tables": [],
        },
        {
            "chunk_id": "c2",
            "content": "two",
            "bc_concepts": [],
            "bc_db_tables": ["orders"],
        },
    ]
