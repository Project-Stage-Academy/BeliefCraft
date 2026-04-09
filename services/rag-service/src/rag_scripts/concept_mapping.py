"""
concept_mapping.py — Single-entry pipeline to enrich ULTIMATE_BOOK_DATA_03_04_translated.json
with bc_concepts and bc_db_tables using AWS Bedrock (claude-haiku-4-5).

Phases:
  1. Tag chunks with concept tags  → chunk_concepts.jsonl   (chunk_id keyed, resumable)
  2. Tag chunks with DB tables     → chunk_bc_tables.jsonl  (chunk_id keyed, resumable)
  3. Merge everything              → ULTIMATE_BOOK_DATA_enriched.json

Usage:
    python concept_mapping.py \
        --input       ULTIMATE_BOOK_DATA_03_04_translated.json \
        --tags-input  concept_tags.json \
        --concepts    chunk_concepts.jsonl \
        --tables      chunk_bc_tables.jsonl \
        --output      ULTIMATE_BOOK_DATA_enriched.json

AWS credentials are read from environment variables / ~/.aws/credentials as usual.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import time
from pathlib import Path
from typing import Any, cast

import boto3
from botocore.config import Config

# ─────────────────────────────────────────────────────────────────────────────
# Bedrock client + model
# ─────────────────────────────────────────────────────────────────────────────

BEDROCK_MODEL_ID = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
BEDROCK_MAX_TOKENS = 8192
BEDROCK_TEMPERATURE = 0.1
ANTHROPIC_VERSION = "bedrock-2023-05-31"

TOKENS_PER_CHAR = 1 / 4  # conservative estimate


def build_bedrock_client() -> Any:
    return boto3.client(
        service_name="bedrock-runtime",
        region_name=os.getenv("AWS_REGION", "us-east-1"),
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        config=Config(read_timeout=600, connect_timeout=60),
    )


def call_bedrock(client: Any, system_prompt: str, user_prompt: str) -> str:
    """Call Bedrock Haiku and return the response text."""
    body = {
        "anthropic_version": ANTHROPIC_VERSION,
        "max_tokens": BEDROCK_MAX_TOKENS,
        "temperature": BEDROCK_TEMPERATURE,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_prompt}],
    }
    response = client.invoke_model(modelId=BEDROCK_MODEL_ID, body=json.dumps(body))
    response_body = json.loads(response["body"].read())
    return cast(str, response_body["content"][0]["text"])


# ─────────────────────────────────────────────────────────────────────────────
# Generic helpers
# ─────────────────────────────────────────────────────────────────────────────


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def load_jsonl(path: Path) -> dict[str, dict[str, Any]]:
    """Load JSONL → dict keyed by chunk_id."""
    result: dict[str, dict[str, Any]] = {}
    if not path.exists():
        return result
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                cid = record.get("chunk_id")
                if cid:
                    result[cid] = record
            except json.JSONDecodeError:
                pass
    return result


def estimate_tokens(text: str) -> int:
    return int(len(text) * TOKENS_PER_CHAR)


def create_batches(
    items: list[dict[str, Any]],
    max_tokens: int,
    rng: random.Random,
) -> list[list[dict[str, Any]]]:
    """Batch by token budget; shuffle first for even distribution."""
    shuffled = items[:]
    rng.shuffle(shuffled)
    batches: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    current_tokens = 0
    for item in shuffled:
        item_tokens = estimate_tokens(item.get("content", "")) + 50
        if current and current_tokens + item_tokens > max_tokens:
            batches.append(current)
            current = []
            current_tokens = 0
        current.append(item)
        current_tokens += item_tokens
    if current:
        batches.append(current)
    return batches


def parse_json_response(text: str) -> Any:
    """Extract JSON from model response (handles ```json fences)."""
    text = text.strip()
    # Strip ```json ... ``` fences if present
    if text.startswith("```"):
        start = text.find("\n") + 1
        end = text.rfind("```")
        text = text[start:end].strip()
    return json.loads(text)


# ─────────────────────────────────────────────────────────────────────────────
# Phase 1 — Tag with concept tags
# ─────────────────────────────────────────────────────────────────────────────

_CONCEPTS_SYSTEM = (
    "You are an expert at mapping technical documentation to structured concept tags "
    "for an autonomous logistics agent. "
    "This agent operates in a warehouse simulation environment (BeliefCraft) with PostgreSQL "
    "backend, making procurement, inventory, and shipment decisions under uncertainty. "
    "Your task is to assign agent concept tags to literature chunks. "
    "Be precise: only assign tags that are clearly relevant to the chunk content "
    "AND useful for agent reasoning in this environment."
)

_CONCEPTS_USER = """\
You are given:
1. A MASTER LIST of AGENT CONCEPT TAGS (SCREAMING_SNAKE_CASE)
2. A BATCH of text chunks from the book "Algorithms for Decision Making"

ABOUT THE AGENT & ENVIRONMENT:
- The agent makes procurement, inventory, and shipment decisions in a warehouse simulation
- Environment data: PostgreSQL tables
    (warehouses, suppliers, routes, shipments, inventory_balances, etc.)
- Key challenges: noisy sensor data, stochastic lead times, SLA constraints,
    dual-objective optimization

AGENT CONCEPT TAGS (select from these only):
{concept_tags}

BATCH CHUNKS:
{batch_chunks}

TASK: For EACH chunk, select 0-10 AGENT CONCEPT TAGS from the MASTER LIST that:
1. Are RELEVANT to the chunk's algorithmic/content focus
2. Would HELP THE AGENT reason about decisions in the warehouse environment
3. Bridge literature concepts <-> agent tools <-> environment data

RULES:
- Only use tags from the provided list — do NOT invent new ones
- If a chunk has no relevant tags, return empty list []
- Be conservative: only assign if clearly useful for agent reasoning
- Return results for ALL {n} chunks in the batch

OUTPUT FORMAT — return ONLY valid compact JSON, no markdown, no preamble:
{{
  "results": [
    {{"chunk_id": "<chunk_id>", "bc_concepts": ["TAG_1", "TAG_2"]}},
    ...
  ]
}}
"""


def tag_concepts_batch(
    client: Any,
    batch: list[dict[str, Any]],
    concept_tags: list[str],
) -> list[dict[str, Any]] | None:
    tags_str = "\n".join(f"- {t}" for t in concept_tags)
    chunks_str = "\n\n".join(f"### Chunk [ID: {c['chunk_id']}]\n{c['content']}" for c in batch)
    prompt = _CONCEPTS_USER.format(
        concept_tags=tags_str,
        batch_chunks=chunks_str,
        n=len(batch),
    )
    try:
        raw = call_bedrock(client, _CONCEPTS_SYSTEM, prompt)
        data = parse_json_response(raw)
        results = data.get("results", [])
        # Validate tags
        tag_set = set(concept_tags)
        return [
            {
                "chunk_id": r["chunk_id"],
                "bc_concepts": [t for t in r.get("bc_concepts", []) if t in tag_set],
            }
            for r in results
            if "chunk_id" in r
        ]
    except Exception as e:
        print(f"  [concepts] batch error: {e}")
        return None


def run_phase1_concepts(
    chunks: list[dict[str, Any]],
    concept_tags: list[str],
    output_path: Path,
    bedrock_client: Any,
    tokens_per_batch: int,
    seed: int,
) -> None:
    """Phase 1: tag all chunks with bc_concepts, write to JSONL (resumable)."""
    print("\n=== Phase 1: Tagging concepts ===")
    already_done = set(load_jsonl(output_path))
    pending = [c for c in chunks if c["chunk_id"] not in already_done]
    print(f"  Total: {len(chunks)}, already done: {len(already_done)}, pending: {len(pending)}")

    if not pending:
        print("  Nothing to do — all chunks already tagged.")
        return

    rng = random.Random(seed)  # noqa: S311
    batches = create_batches(pending, tokens_per_batch, rng)
    print(f"  Batches: {len(batches)}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("a", encoding="utf-8") as out_f:
        for i, batch in enumerate(batches):
            print(f"  Batch {i + 1}/{len(batches)} ({len(batch)} chunks) ...", end=" ")
            results = tag_concepts_batch(bedrock_client, batch, concept_tags)
            if results:
                for r in results:
                    out_f.write(json.dumps(r, ensure_ascii=False) + "\n")
                out_f.flush()
                print(f"OK ({len(results)} tagged)")
            else:
                # Write empty entries so we don't retry on next run
                for c in batch:
                    out_f.write(
                        json.dumps(
                            {"chunk_id": c["chunk_id"], "bc_concepts": []}, ensure_ascii=False
                        )
                        + "\n"
                    )
                out_f.flush()
                print("FAILED — wrote empty entries")
            time.sleep(0.3)

    print(f"  Phase 1 done → {output_path}")


# ─────────────────────────────────────────────────────────────────────────────
# Phase 2 — Tag with DB tables
# ─────────────────────────────────────────────────────────────────────────────

DB_TABLES = [
    "warehouses",
    "suppliers",
    "leadtime_models",
    "routes",
    "shipments",
    "products",
    "locations",
    "inventory_balances",
    "inventory_moves",
    "orders",
    "order_lines",
    "purchase_orders",
    "po_lines",
    "sensor_devices",
    "observations",
]

DB_TABLE_DESCRIPTIONS = {
    "warehouses": "Facility metadata: id, name, region, timezone",
    "suppliers": "Supplier info: id, name, reliability_score, region",
    "leadtime_models": "Stochastic lead time distributions: dist_family, parameters",
    "routes": "Transport routes: origin/destination, mode (truck/air/rail/sea), distance",
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

_TABLES_SYSTEM = (
    "You are an expert at mapping technical documentation to database schema references. "
    "This documentation is used by an autonomous logistics agent operating in BeliefCraft warehouse"
    " simulation. Your task is to assign relevant PostgreSQL table names to literature chunks. "
    "Be precise: only assign tables that are clearly relevant to the chunk content."
)

_TABLES_USER = """\
You are given:
1. A LIST of DATABASE TABLES with brief descriptions
2. A BATCH of text chunks from the book "Algorithms for Decision Making"

DATABASE TABLES (select from these only):
{db_tables}

BATCH CHUNKS:
{batch_chunks}

TASK: For EACH chunk, select 0-5 DB tables whose data is clearly relevant to this chunk's content.

RULES:
- Only use tables from the provided list — do NOT invent new ones
- If a chunk has no relevant tables, return empty list []
- Be conservative
- Return results for ALL {n} chunks

OUTPUT FORMAT — return ONLY valid compact JSON, no markdown, no preamble:
{{
  "results": [
    {{"chunk_id": "<chunk_id>", "bc_db_tables": ["table1", "table2"]}},
    ...
  ]
}}
"""


def tag_tables_batch(
    client: Any,
    batch: list[dict[str, Any]],
) -> list[dict[str, Any]] | None:
    tables_str = "\n".join(f"- {tbl}: {DB_TABLE_DESCRIPTIONS.get(tbl, '')}" for tbl in DB_TABLES)
    chunks_str = "\n\n".join(f"### Chunk [ID: {c['chunk_id']}]\n{c['content']}" for c in batch)
    prompt = _TABLES_USER.format(
        db_tables=tables_str,
        batch_chunks=chunks_str,
        n=len(batch),
    )
    try:
        raw = call_bedrock(client, _TABLES_SYSTEM, prompt)
        data = parse_json_response(raw)
        results = data.get("results", [])
        table_set = set(DB_TABLES)
        return [
            {
                "chunk_id": r["chunk_id"],
                "bc_db_tables": [t for t in r.get("bc_db_tables", []) if t in table_set],
            }
            for r in results
            if "chunk_id" in r
        ]
    except Exception as e:
        print(f"  [tables] batch error: {e}")
        return None


def run_phase2_tables(
    chunks: list[dict[str, Any]],
    output_path: Path,
    bedrock_client: Any,
    tokens_per_batch: int,
    seed: int,
) -> None:
    """Phase 2: tag all chunks with bc_db_tables, write to JSONL (resumable)."""
    print("\n=== Phase 2: Tagging DB tables ===")
    already_done = set(load_jsonl(output_path))
    pending = [c for c in chunks if c["chunk_id"] not in already_done]
    print(f"  Total: {len(chunks)}, already done: {len(already_done)}, pending: {len(pending)}")

    if not pending:
        print("  Nothing to do — all chunks already tagged.")
        return

    rng = random.Random(seed)  # noqa: S311
    batches = create_batches(pending, tokens_per_batch, rng)
    print(f"  Batches: {len(batches)}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("a", encoding="utf-8") as out_f:
        for i, batch in enumerate(batches):
            print(f"  Batch {i + 1}/{len(batches)} ({len(batch)} chunks) ...", end=" ")
            results = tag_tables_batch(bedrock_client, batch)
            if results:
                for r in results:
                    out_f.write(json.dumps(r, ensure_ascii=False) + "\n")
                out_f.flush()
                print(f"OK ({len(results)} tagged)")
            else:
                for c in batch:
                    out_f.write(
                        json.dumps(
                            {"chunk_id": c["chunk_id"], "bc_db_tables": []}, ensure_ascii=False
                        )
                        + "\n"
                    )
                out_f.flush()
                print("FAILED — wrote empty entries")
            time.sleep(0.3)

    print(f"  Phase 2 done → {output_path}")


# ─────────────────────────────────────────────────────────────────────────────
# Phase 3 — Merge into final JSON
# ─────────────────────────────────────────────────────────────────────────────


def run_phase3_merge(
    chunks: list[dict[str, Any]],
    concepts_path: Path,
    tables_path: Path,
    output_path: Path,
) -> None:
    """Phase 3: merge JSONL tags into main chunk list and write enriched JSON."""
    print("\n=== Phase 3: Merging into enriched JSON ===")

    concepts_map = {cid: v.get("bc_concepts", []) for cid, v in load_jsonl(concepts_path).items()}
    tables_map = {cid: v.get("bc_db_tables", []) for cid, v in load_jsonl(tables_path).items()}
    print(f"  Loaded {len(concepts_map)} concept entries, {len(tables_map)} table entries.")

    matched_c = matched_t = 0
    for chunk in chunks:
        cid = chunk.get("chunk_id")
        if cid in concepts_map:
            chunk["bc_concepts"] = concepts_map[cid]
            matched_c += 1
        else:
            chunk["bc_concepts"] = []

        if cid in tables_map:
            chunk["bc_db_tables"] = tables_map[cid]
            matched_t += 1
        else:
            chunk["bc_db_tables"] = []

    print(
        f"  Concepts matched: {matched_c}/{len(chunks)}, Tables matched: {matched_t}/{len(chunks)}"
    )

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(chunks, f, ensure_ascii=False, indent=2)
    print(f"  Written → {output_path}")


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Enrich ULTIMATE_BOOK_DATA with bc_concepts and bc_db_tables via Bedrock Haiku."
    )
    p.add_argument("--input", type=Path, default=Path("ULTIMATE_BOOK_DATA_03_04_translated.json"))
    p.add_argument(
        "--tags-input",
        type=Path,
        default=Path("concept_tags.json"),
        help="concept_tags.json from Phase 1 (must have 'tags' key)",
    )
    p.add_argument(
        "--concepts",
        type=Path,
        default=Path("chunk_concepts.jsonl"),
        help="Intermediate: concept tags per chunk",
    )
    p.add_argument(
        "--tables",
        type=Path,
        default=Path("chunk_bc_tables.jsonl"),
        help="Intermediate: DB tables per chunk",
    )
    p.add_argument("--output", type=Path, default=Path("ULTIMATE_BOOK_DATA_enriched.json"))
    p.add_argument(
        "--tokens-per-batch", type=int, default=6000, help="Approximate token budget per LLM batch"
    )
    p.add_argument("--seed", type=int, default=42)
    p.add_argument(
        "--skip-concepts", action="store_true", help="Skip Phase 1 (concepts already in JSONL)"
    )
    p.add_argument(
        "--skip-tables", action="store_true", help="Skip Phase 2 (tables already in JSONL)"
    )
    p.add_argument(
        "--merge-only", action="store_true", help="Skip Phases 1 & 2, only run merge (Phase 3)"
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()

    # ── Load source data ──────────────────────────────────────────────────────
    print(f"Loading {args.input} ...")
    chunks: list[dict[str, Any]] = load_json(args.input)
    # Keep only chunks that have content — skip empty
    chunks_with_content = [c for c in chunks if c.get("content", "").strip()]
    print(f"  Total chunks: {len(chunks)}, with content: {len(chunks_with_content)}")

    skip_concepts = args.skip_concepts or args.merge_only
    skip_tables = args.skip_tables or args.merge_only

    if not skip_concepts or not skip_tables:
        bedrock_client = build_bedrock_client()

    # ── Phase 1 ───────────────────────────────────────────────────────────────
    if not skip_concepts:
        print(f"Loading concept tags from {args.tags_input} ...")
        tags_data = load_json(args.tags_input)
        concept_tags: list[str] = tags_data.get("tags", [])
        if not concept_tags:
            raise ValueError(f"No tags found in {args.tags_input} (expected key 'tags')")
        print(f"  Loaded {len(concept_tags)} concept tags.")
        run_phase1_concepts(
            chunks=chunks_with_content,
            concept_tags=concept_tags,
            output_path=args.concepts,
            bedrock_client=bedrock_client,
            tokens_per_batch=args.tokens_per_batch,
            seed=args.seed,
        )
    else:
        print("\nSkipping Phase 1 (concepts).")

    # ── Phase 2 ───────────────────────────────────────────────────────────────
    if not skip_tables:
        run_phase2_tables(
            chunks=chunks_with_content,
            output_path=args.tables,
            bedrock_client=bedrock_client,
            tokens_per_batch=args.tokens_per_batch,
            seed=args.seed,
        )
    else:
        print("Skipping Phase 2 (tables).")

    # ── Phase 3 ───────────────────────────────────────────────────────────────
    run_phase3_merge(
        chunks=chunks,  # merge into ALL chunks (including those without content)
        concepts_path=args.concepts,
        tables_path=args.tables,
        output_path=args.output,
    )

    print("\n✅ All done.")


if __name__ == "__main__":
    main()
