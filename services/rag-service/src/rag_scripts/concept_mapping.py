"""
concept_mapping.py — Enrich ULTIMATE_BOOK_DATA with bc_concepts and bc_db_tables
using LangChain + langchain-aws (ChatBedrock / claude-haiku-4-5).

Steps:
  1. Tag chunks with concept tags  → chunk_concepts.jsonl   (resumable)
  2. Tag chunks with DB tables     → chunk_bc_tables.jsonl  (resumable)
  3. Merge everything              → ULTIMATE_BOOK_DATA_enriched.json

Usage:
    python concept_mapping.py \
        --input       ULTIMATE_BOOK_DATA_03_04_translated.json \
        --tags-input  concept_tags.json \
        --concepts    chunk_concepts.jsonl \
        --tables      chunk_bc_tables.jsonl \
        --output      ULTIMATE_BOOK_DATA_enriched.json
"""

from __future__ import annotations

import argparse
import json
import random
from collections.abc import Callable
from pathlib import Path
from typing import Any

from langchain_aws import ChatBedrock
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable
from pydantic import BaseModel, Field


class ConceptResult(BaseModel):
    chunk_id: str
    bc_concepts: list[str] = Field(default_factory=list)


class ConceptBatch(BaseModel):
    results: list[ConceptResult]


class TableResult(BaseModel):
    chunk_id: str
    bc_db_tables: list[str] = Field(default_factory=list)


class TableBatch(BaseModel):
    results: list[TableResult]


MODEL_ID = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
TOKENS_PER_CHAR = 1 / 4

DB_TABLES: dict[str, str] = {
    "warehouses": "Facility metadata: id, name, region, timezone",
    "suppliers": "Supplier info: id, name, reliability_score, region",
    "leadtime_models": "Stochastic lead time distributions: dist_family, parameters",
    "routes": "Transport routes: origin/destination, mode, distance",
    "shipments": "Shipment records: direction, order/PO links, route, status, timestamps",
    "products": "Product catalog: sku, name, category, shelf_life_days",
    "locations": "Warehouse layout: shelf/bin/pallet positions, capacity, hierarchy",
    "inventory_balances": "Current stock: on_hand, reserved, quality_status per product/location",
    "inventory_moves": "Stock movement history: transfers, adjustments, inbound/outbound",
    "orders": "Customer orders: status, promised_at, sla_priority, requested region",
    "order_lines": "Order line items: qty_ordered/allocated/shipped, service_level_penalty",
    "purchase_orders": "Procurement orders: supplier, destination warehouse, status, expected_at",
    "po_lines": "PO line items: product, qty_ordered/received",
    "sensor_devices": "IoT sensors: device_type, noise_sigma, missing_rate, bias, status",
    "observations": "Noisy sensor readings: observed_qty, confidence, is_missing",
}


def build_llm() -> ChatBedrock:
    return ChatBedrock(
        model=MODEL_ID,
        model_kwargs={"max_tokens": 8192, "temperature": 0.1},
    )


def make_chain(
    llm: ChatBedrock, schema: type[BaseModel], prompt: ChatPromptTemplate
) -> Runnable[dict[str, Any], Any]:
    return prompt | llm.with_structured_output(schema).with_retry(stop_after_attempt=3)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    result: dict[str, dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                rec: dict[str, Any] = json.loads(line)
                if cid := rec.get("chunk_id"):
                    result[cid] = rec
            except json.JSONDecodeError:
                pass
    return result


def append_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def create_batches(
    items: list[dict[str, Any]], max_tokens: int, rng: random.Random
) -> list[list[dict[str, Any]]]:
    shuffled = items[:]
    rng.shuffle(shuffled)
    batches: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    current_tokens = 0
    for item in shuffled:
        cost = int(len(item.get("content", "")) * TOKENS_PER_CHAR) + 50
        if current and current_tokens + cost > max_tokens:
            batches.append(current)
            current, current_tokens = [], 0
        current.append(item)
        current_tokens += cost
    if current:
        batches.append(current)
    return batches


def format_chunks(batch: list[dict[str, Any]]) -> str:
    return "\n\n".join(f"### Chunk [ID: {c['chunk_id']}]\n{c['content']}" for c in batch)


def _run_tagging(
    step_name: str,
    chunks: list[dict[str, Any]],
    output_path: Path,
    tokens_per_batch: int,
    seed: int,
    tag_fn: Callable[[list[dict[str, Any]]], list[dict[str, Any]] | None],
    empty_record_fn: Callable[[str], dict[str, Any]],
) -> None:
    print(f"\n=== {step_name} ===")
    done = set(load_jsonl(output_path))
    pending = [c for c in chunks if c["chunk_id"] not in done]
    print(f"  Total: {len(chunks)}, done: {len(done)}, pending: {len(pending)}")
    if not pending:
        print("  Nothing to do.")
        return

    batches = create_batches(pending, tokens_per_batch, random.Random(seed))  # noqa: S311
    print(f"  Batches: {len(batches)}")

    for i, batch in enumerate(batches):
        print(f"  Batch {i + 1}/{len(batches)} ({len(batch)} chunks) ...", end=" ")
        results = tag_fn(batch)
        if results:
            append_jsonl(output_path, results)
            print(f"OK ({len(results)} tagged)")
        else:
            append_jsonl(output_path, [empty_record_fn(c["chunk_id"]) for c in batch])
            print("FAILED — wrote empty entries")

    print(f"  Done → {output_path}")


_CONCEPTS_SYSTEM = (
    "You are an expert at mapping technical documentation to structured concept tags "
    "for an autonomous logistics agent operating in a warehouse simulation (BeliefCraft) "
    "with a PostgreSQL backend. Assign only tags clearly relevant to the chunk content "
    "and useful for agent reasoning."
)

_concepts_prompt = ChatPromptTemplate.from_messages(
    [
        ("system", _CONCEPTS_SYSTEM),
        (
            "human",
            """\
AGENT CONCEPT TAGS (select from these only):
{concept_tags}

BATCH CHUNKS:
{batch_chunks}

For EACH chunk select 0-10 tags that:
1. Are relevant to the chunk's algorithmic focus
2. Help the agent reason about warehouse decisions
3. Bridge literature concepts ↔ agent tools ↔ environment data

Rules: only use provided tags; empty list [] if none apply; be conservative.
Return results for ALL {n} chunks.
""",
        ),
    ]
)


def _tag_concepts(
    chain: Runnable[dict[str, Any], Any],
    batch: list[dict[str, Any]],
    concept_tags: list[str],
) -> list[dict[str, Any]] | None:
    try:
        result: ConceptBatch = chain.invoke(
            {
                "concept_tags": "\n".join(f"- {t}" for t in concept_tags),
                "batch_chunks": format_chunks(batch),
                "n": len(batch),
            }
        )
        tag_set = set(concept_tags)
        return [
            {"chunk_id": r.chunk_id, "bc_concepts": [t for t in r.bc_concepts if t in tag_set]}
            for r in result.results
        ]
    except Exception as e:
        print(f"\n  [concepts] error: {e}")
        return None


def tag_concepts(
    chunks: list[dict[str, Any]],
    concept_tags: list[str],
    output_path: Path,
    llm: ChatBedrock,
    tokens_per_batch: int,
    seed: int,
) -> None:
    chain = make_chain(llm, ConceptBatch, _concepts_prompt)
    _run_tagging(
        "Tagging concepts",
        chunks,
        output_path,
        tokens_per_batch,
        seed,
        tag_fn=lambda batch: _tag_concepts(chain, batch, concept_tags),
        empty_record_fn=lambda cid: {"chunk_id": cid, "bc_concepts": []},
    )


_TABLES_SYSTEM = (
    "You are an expert at mapping technical documentation to database schema references "
    "for an autonomous logistics agent in a BeliefCraft warehouse simulation. "
    "Assign only tables clearly relevant to the chunk content."
)

_tables_prompt = ChatPromptTemplate.from_messages(
    [
        ("system", _TABLES_SYSTEM),
        (
            "human",
            """\
DATABASE TABLES (select from these only):
{db_tables}

BATCH CHUNKS:
{batch_chunks}

For EACH chunk select 0-5 tables whose data is clearly relevant.
Rules: only use provided tables; empty list [] if none; be conservative.
Return results for ALL {n} chunks.
""",
        ),
    ]
)


def _tag_tables(
    chain: Runnable[dict[str, Any], Any],
    batch: list[dict[str, Any]],
) -> list[dict[str, Any]] | None:
    try:
        result: TableBatch = chain.invoke(
            {
                "db_tables": "\n".join(f"- {t}: {desc}" for t, desc in DB_TABLES.items()),
                "batch_chunks": format_chunks(batch),
                "n": len(batch),
            }
        )
        table_set = set(DB_TABLES)
        return [
            {"chunk_id": r.chunk_id, "bc_db_tables": [t for t in r.bc_db_tables if t in table_set]}
            for r in result.results
        ]
    except Exception as e:
        print(f"\n  [tables] error: {e}")
        return None


def tag_tables(
    chunks: list[dict[str, Any]],
    output_path: Path,
    llm: ChatBedrock,
    tokens_per_batch: int,
    seed: int,
) -> None:
    chain = make_chain(llm, TableBatch, _tables_prompt)
    _run_tagging(
        "Tagging DB tables",
        chunks,
        output_path,
        tokens_per_batch,
        seed,
        tag_fn=lambda batch: _tag_tables(chain, batch),
        empty_record_fn=lambda cid: {"chunk_id": cid, "bc_db_tables": []},
    )


def merge(
    chunks: list[dict[str, Any]],
    concepts_path: Path,
    tables_path: Path,
    output_path: Path,
) -> None:
    print("\n=== Merging ===")
    concepts_map = {cid: v.get("bc_concepts", []) for cid, v in load_jsonl(concepts_path).items()}
    tables_map = {cid: v.get("bc_db_tables", []) for cid, v in load_jsonl(tables_path).items()}
    print(f"  Concepts: {len(concepts_map)}, Tables: {len(tables_map)}")

    matched_c = matched_t = 0
    for chunk in chunks:
        cid: str | None = chunk.get("chunk_id")
        if cid is None:
            chunk["bc_concepts"] = []
            chunk["bc_db_tables"] = []
            continue
        chunk["bc_concepts"] = concepts_map.get(cid, [])
        chunk["bc_db_tables"] = tables_map.get(cid, [])
        if cid in concepts_map:
            matched_c += 1
        if cid in tables_map:
            matched_t += 1

    output_path.write_text(json.dumps(chunks, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"  Concepts matched: {matched_c}/{len(chunks)}, Tables matched: {matched_t}/{len(chunks)}"
    )
    print(f"  Written → {output_path}")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Enrich ULTIMATE_BOOK_DATA via LangChain + Bedrock.")
    p.add_argument("--input", type=Path, default=Path("ULTIMATE_BOOK_DATA_03_04_translated.json"))
    p.add_argument("--tags-input", type=Path, default=Path("concept_tags.json"))
    p.add_argument("--concepts", type=Path, default=Path("chunk_concepts.jsonl"))
    p.add_argument("--tables", type=Path, default=Path("chunk_bc_tables.jsonl"))
    p.add_argument("--output", type=Path, default=Path("ULTIMATE_BOOK_DATA_enriched.json"))
    p.add_argument("--tokens-per-batch", type=int, default=6000)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--skip-concepts", action="store_true")
    p.add_argument("--skip-tables", action="store_true")
    p.add_argument("--merge-only", action="store_true")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    print(f"Loading {args.input} ...")
    all_chunks: list[dict[str, Any]] = load_json(args.input)
    chunks = [c for c in all_chunks if c.get("content", "").strip()]
    print(f"  Total: {len(all_chunks)}, with content: {len(chunks)}")

    skip_concepts = args.skip_concepts or args.merge_only
    skip_tables = args.skip_tables or args.merge_only
    llm: ChatBedrock = build_llm()

    if not skip_concepts:
        tags_data: dict[str, Any] = load_json(args.tags_input)
        concept_tags: list[str] = tags_data.get("tags", [])
        if not concept_tags:
            raise ValueError(f"No tags found in {args.tags_input} (expected key 'tags')")
        print(f"  Loaded {len(concept_tags)} concept tags.")
        tag_concepts(chunks, concept_tags, args.concepts, llm, args.tokens_per_batch, args.seed)
    else:
        print("\nSkipping concepts.")

    if not skip_tables:
        tag_tables(chunks, args.tables, llm, args.tokens_per_batch, args.seed)
    else:
        print("Skipping DB tables.")

    merge(all_chunks, args.concepts, args.tables, args.output)
    print("\nAll done.")


if __name__ == "__main__":
    main()
