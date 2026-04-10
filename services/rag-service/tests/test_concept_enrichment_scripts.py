import importlib
import json
import sys
import types
from pathlib import Path
from typing import Any

import pytest


@pytest.fixture()
def script_modules(monkeypatch: pytest.MonkeyPatch) -> tuple[Any, Any]:
    """Import script modules with lightweight langchain stubs for unit tests."""
    fake_langchain_aws = types.ModuleType("langchain_aws")

    class FakeChatBedrock:
        def __init__(self, *args: Any, **kwargs: Any) -> None:  # noqa: ANN002, ANN003
            self.args = args
            self.kwargs = kwargs

        def with_structured_output(self, schema: Any) -> "FakeChatBedrock":
            return self

        def with_retry(self, stop_after_attempt: int) -> "FakeChatBedrock":  # noqa: ARG002
            return self

    fake_langchain_aws.ChatBedrock = FakeChatBedrock

    fake_prompts = types.ModuleType("langchain_core.prompts")

    class FakeChatPromptTemplate:
        @classmethod
        def from_messages(
            cls, messages: list[tuple[str, str]]
        ) -> "FakeChatPromptTemplate":  # noqa: ARG003
            return cls()

    fake_prompts.ChatPromptTemplate = FakeChatPromptTemplate

    fake_runnables = types.ModuleType("langchain_core.runnables")

    class FakeRunnable:
        pass

    fake_runnables.Runnable = FakeRunnable

    monkeypatch.setitem(sys.modules, "langchain_aws", fake_langchain_aws)
    monkeypatch.setitem(sys.modules, "langchain_core.prompts", fake_prompts)
    monkeypatch.setitem(sys.modules, "langchain_core.runnables", fake_runnables)

    sys.modules.pop("rag_scripts.concept_mapping", None)
    sys.modules.pop("rag_scripts.concept_tags_generator", None)

    cm = importlib.import_module("rag_scripts.concept_mapping")
    ctg = importlib.import_module("rag_scripts.concept_tags_generator")
    return cm, ctg


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("belief update", "BELIEF_UPDATE"),
        ("Belief-Update", "BELIEF_UPDATE"),
        ("already_ok", "ALREADY_OK"),
        ("??", None),
    ],
)
def test_concept_tags_normalize_tag(
    script_modules: tuple[Any, Any], raw: str, expected: str | None
) -> None:
    _, ctg = script_modules

    assert ctg.normalize_tag(raw) == expected


def test_concept_tags_deduplicate_tags_removes_duplicates_and_invalid(
    script_modules: tuple[Any, Any],
) -> None:
    _, ctg = script_modules
    raw_tags = ["belief update", "BELIEF_UPDATE", "ok_tag", "??", "ok-tag"]

    deduped = ctg.deduplicate_tags(raw_tags)

    assert deduped == ["BELIEF_UPDATE", "OK_TAG"]


def test_concept_tags_semantic_deduplicate_tags_filters_semantic_duplicates(
    script_modules: tuple[Any, Any],
) -> None:
    _, ctg = script_modules

    class FakeChain:
        def invoke(self, payload: dict[str, Any]) -> Any:
            assert "BELIEF_UPDATE" in payload["tags_text"]
            return ctg.CanonicalTagList(tags=["BELIEF_UPDATE", "STOCKOUT_RISK"])

    raw_tags = [
        "belief update",
        "bayesian_belief_update",
        "stockout risk",
        "STOCKOUT_RISK",
    ]

    deduped = ctg.semantic_deduplicate_tags(raw_tags, FakeChain())

    assert deduped == ["BELIEF_UPDATE", "STOCKOUT_RISK"]


def test_concept_tags_semantic_deduplicate_tags_falls_back_on_chain_failure(
    script_modules: tuple[Any, Any],
) -> None:
    _, ctg = script_modules

    class FailingChain:
        def invoke(self, payload: dict[str, Any]) -> Any:  # noqa: ARG002
            raise RuntimeError("bedrock timeout")

    raw_tags = ["belief update", "BELIEF_UPDATE", "ok_tag"]

    deduped = ctg.semantic_deduplicate_tags(raw_tags, FailingChain())

    assert deduped == ["BELIEF_UPDATE", "OK_TAG"]


def test_concept_tags_semantic_deduplicate_tags_drops_hallucinated_tags(
    script_modules: tuple[Any, Any],
) -> None:
    _, ctg = script_modules

    class FakeChain:
        def invoke(self, payload: dict[str, Any]) -> Any:  # noqa: ARG002
            return ctg.CanonicalTagList(tags=["BELIEF_UPDATE", "INVENTED_TAG"])

    raw_tags = ["belief update", "ok_tag"]

    deduped = ctg.semantic_deduplicate_tags(raw_tags, FakeChain())

    assert deduped == ["BELIEF_UPDATE"]


def test_concept_mapping_load_jsonl_handles_invalid_lines(
    script_modules: tuple[Any, Any], tmp_path: Path
) -> None:
    cm, _ = script_modules
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


def test_concept_mapping_create_batches_respects_token_budget(
    script_modules: tuple[Any, Any],
) -> None:
    cm, _ = script_modules

    class DeterministicRng:
        def shuffle(self, sequence: list[dict[str, Any]]) -> None:  # noqa: ARG002
            return None

    items = [
        {"chunk_id": "c1", "content": "a" * 200},
        {"chunk_id": "c2", "content": "b" * 200},
        {"chunk_id": "c3", "content": "c" * 200},
    ]

    batches = cm.create_batches(items, max_tokens=299, rng=DeterministicRng())

    assert [len(batch) for batch in batches] == [2, 1]


def test_concept_mapping_tag_concepts_filters_unknown_tags(script_modules: tuple[Any, Any]) -> None:
    cm, _ = script_modules

    class FakeChain:
        def invoke(self, payload: dict[str, Any]) -> Any:  # noqa: ARG002
            return cm.ConceptBatch(
                results=[
                    cm.ConceptResult(chunk_id="c1", bc_concepts=["KNOWN", "UNKNOWN"]),
                    cm.ConceptResult(chunk_id="c2", bc_concepts=[]),
                ]
            )

    result = cm._tag_concepts(  # noqa: SLF001
        chain=FakeChain(),
        batch=[{"chunk_id": "c1", "content": "a"}, {"chunk_id": "c2", "content": "b"}],
        concept_tags=["KNOWN"],
    )

    assert result == [
        {"chunk_id": "c1", "bc_concepts": ["KNOWN"]},
        {"chunk_id": "c2", "bc_concepts": []},
    ]


def test_concept_mapping_tag_tables_filters_unknown_tables(script_modules: tuple[Any, Any]) -> None:
    cm, _ = script_modules

    class FakeChain:
        def invoke(self, payload: dict[str, Any]) -> Any:  # noqa: ARG002
            return cm.TableBatch(
                results=[
                    cm.TableResult(chunk_id="c1", bc_db_tables=["orders", "not_a_table"]),
                    cm.TableResult(chunk_id="c2", bc_db_tables=[]),
                ]
            )

    result = cm._tag_tables(  # noqa: SLF001
        chain=FakeChain(),
        batch=[{"chunk_id": "c1", "content": "a"}, {"chunk_id": "c2", "content": "b"}],
    )

    assert result == [
        {"chunk_id": "c1", "bc_db_tables": ["orders"]},
        {"chunk_id": "c2", "bc_db_tables": []},
    ]


def test_concept_mapping_merge_fills_missing_tags(
    script_modules: tuple[Any, Any], tmp_path: Path
) -> None:
    cm, _ = script_modules

    chunks = [
        {"chunk_id": "c1", "content": "one"},
        {"chunk_id": "c2", "content": "two"},
        {"content": "missing id"},
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

    cm.merge(chunks, concepts_path, tables_path, output_path)

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
        {
            "content": "missing id",
            "bc_concepts": [],
            "bc_db_tables": [],
        },
    ]
