"""
Concept Tag Generator — Phase 1: Extract generalized, reusable concept tags from literature chunks.

This script:
1. Loads all text chunks from ULTIMATE_BOOK_DATA_03_04_translated.json
2. Groups them into LLM-sized batches
3. Asks AWS Bedrock Haiku to generate generalized concept tags (SCREAMING_SNAKE_CASE)
4. Deduplicates and normalizes the tag list
5. Outputs: concept_tags.json — a simple list of reusable tags

Usage:
    python concept_tags_generator.py \
        --input  ULTIMATE_BOOK_DATA_03_04_translated.json \
        --output concept_tags.json \
        --tokens-per-batch 6000 \
        --seed 42
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import time
from pathlib import Path
from typing import Any, cast

import boto3
from botocore.config import Config

# ─────────────────────────────────────────────────────────────────────────────
# Bedrock config
# ─────────────────────────────────────────────────────────────────────────────

BEDROCK_MODEL_ID = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
BEDROCK_MAX_TOKENS = 2048
BEDROCK_TEMPERATURE = 0.3
ANTHROPIC_VERSION = "bedrock-2023-05-31"

TOKENS_PER_CHAR = 1 / 4

DB_BRIEF_DESCRIPTION = """
BeliefCraft is a warehouse simulation & analytics platform with PostgreSQL backend.
Core domains: logistics (warehouses, suppliers, routes, shipments), inventory
(products, locations, stock moves),
procurement (purchase orders, suppliers), and observability (sensor devices, noisy observations).
The agent uses this data for decision-making under uncertainty.
"""

# ─────────────────────────────────────────────────────────────────────────────
# Prompts
# ─────────────────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = (
    "You are an expert at extracting high-level, reusable concept tags from technical documentation"
    ". These tags will power an autonomous logistics agent that reasons about algorithms, data, and"
    " constraints. Generate tags that are GENERAL enough to apply to multiple chunks across the "
    "book, but SPECIFIC enough to be useful for retrieval and agent reasoning."
)

_USER_PROMPT = """\
You are given a batch of text chunks from the book "Algorithms for Decision Making".

DATABASE CONTEXT (brief):
{db_description}

BATCH CONTENT (multiple chunks concatenated):
{batch_content}

TASK: Generate generalized concept tags that:
1. Are REUSABLE: Should apply to multiple chunks/sections of the book, not just this batch
2. Are ACTIONABLE: Help an agent decide which algorithm/tool/constraint to use
3. Bridge domains: Connect literature concepts <-> warehouse data <-> agent decisions
4. Follow format: SCREAMING_SNAKE_CASE, concise, descriptive (e.g., "STOCHASTIC_OPTIMIZATION")

GOOD EXAMPLES:
- POMDP_BELIEF_UPDATE (algorithm for uncertain state estimation)
- LEADTIME_RISK_ASSESSMENT (evaluating delivery time uncertainty)
- INVENTORY_RECONCILIATION (matching observed vs. recorded stock)
- CONSTRAINT_FEASIBILITY_CHECK (validating if requirements can be met)

BAD EXAMPLES (too specific or vague):
- chapter_7_pomdp_intro (too chunk-specific)
- optimization (too vague)
- markov_decision_processes_with_partial_observability_and_belief_states (too long)

OUTPUT FORMAT — return ONLY valid compact JSON, no markdown, no preamble:
{{"tags": ["TAG_ONE", "TAG_TWO", ...]}}
"""


# ─────────────────────────────────────────────────────────────────────────────
# Bedrock client
# ─────────────────────────────────────────────────────────────────────────────


def build_bedrock_client() -> Any:
    return boto3.client(
        service_name="bedrock-runtime",
        region_name=os.getenv("AWS_REGION", "us-east-1"),
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        config=Config(read_timeout=600, connect_timeout=60),
    )


def call_bedrock(client: Any, system_prompt: str, user_prompt: str) -> str:
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


def parse_json_response(text: str) -> Any:
    text = text.strip()
    if text.startswith("```"):
        start = text.find("\n") + 1
        end = text.rfind("```")
        text = text[start:end].strip()
    return json.loads(text)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def estimate_tokens(text: str) -> int:
    return int(len(text) * TOKENS_PER_CHAR)


def normalize_tag(tag: str) -> str | None:
    tag = tag.strip().upper().replace(" ", "_").replace("-", "_")
    tag = re.sub(r"[^A-Z0-9_]", "", tag)
    if re.match(r"^[A-Z][A-Z0-9_]*$", tag) and len(tag) >= 3:
        return tag
    return None


def deduplicate_tags(tags: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for tag in sorted(tags, key=len, reverse=True):
        normalized = normalize_tag(tag)
        if not normalized or normalized in seen:
            continue
        if not any(normalized in s or s in normalized for s in seen):
            seen.add(normalized)
            result.append(normalized)
    return result


def load_chunks_from_json(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as f:
        all_chunks = json.load(f)
    return [c for c in all_chunks if c.get("content", "").strip()]


def create_batches(
    chunks: list[dict[str, Any]],
    max_tokens: int,
    rng: random.Random,
) -> list[list[dict[str, Any]]]:
    shuffled = chunks[:]
    rng.shuffle(shuffled)
    batches: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    current_tokens = 0
    for chunk in shuffled:
        chunk_tokens = estimate_tokens(chunk["content"])
        if current and current_tokens + chunk_tokens > max_tokens:
            batches.append(current)
            current = []
            current_tokens = 0
        current.append(chunk)
        current_tokens += chunk_tokens
    if current:
        batches.append(current)
    return batches


# ─────────────────────────────────────────────────────────────────────────────
# LLM call
# ─────────────────────────────────────────────────────────────────────────────


def generate_tags_for_batch(client: Any, batch: list[dict[str, Any]]) -> list[str]:
    batch_content = "\n\n---\n\n".join(
        f"[Chunk {i + 1}] {c['content']}" for i, c in enumerate(batch)
    )
    prompt = _USER_PROMPT.format(
        db_description=DB_BRIEF_DESCRIPTION,
        batch_content=batch_content,
    )
    try:
        raw = call_bedrock(client, _SYSTEM_PROMPT, prompt)
        data = parse_json_response(raw)
        raw_tags: list[str] = data.get("tags", [])
        return [t for t in (normalize_tag(tag) for tag in raw_tags) if t]
    except Exception as e:
        print(f"  [error] batch failed: {e}")
        return []


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Generate concept tags via AWS Bedrock Haiku.")
    p.add_argument("--input", type=Path, default=Path("ULTIMATE_BOOK_DATA_03_04_translated.json"))
    p.add_argument("--output", type=Path, default=Path("concept_tags.json"))
    p.add_argument("--tokens-per-batch", type=int, default=6000)
    p.add_argument("--seed", type=int, default=42)
    return p.parse_args()


def main() -> None:
    args = parse_args()

    print(f"Loading chunks from {args.input} ...")
    chunks = load_chunks_from_json(args.input)
    print(f"  Loaded {len(chunks)} chunks with content.")

    client = build_bedrock_client()
    rng = random.Random(args.seed)  # noqa: S311
    batches = create_batches(chunks, args.tokens_per_batch, rng)
    print(f"  Batches: {len(batches)}")

    all_raw_tags: list[str] = []
    for i, batch in enumerate(batches):
        print(f"  Batch {i + 1}/{len(batches)} ({len(batch)} chunks) ...", end=" ")
        tags = generate_tags_for_batch(client, batch)
        all_raw_tags.extend(tags)
        print(f"OK ({len(tags)} tags)")
        time.sleep(0.3)

    unique_tags = deduplicate_tags(all_raw_tags)
    print(f"\n  Raw tags: {len(all_raw_tags)}, unique after dedup: {len(unique_tags)}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as f:
        json.dump({"tags": unique_tags}, f, indent=2, ensure_ascii=False)

    print(f"\n✅ Saved {len(unique_tags)} tags → {args.output}")
    print("Sample:", unique_tags[:10])


if __name__ == "__main__":
    main()
