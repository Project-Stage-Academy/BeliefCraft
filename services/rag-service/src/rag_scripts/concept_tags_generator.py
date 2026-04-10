"""
concept_tags_generator.py — Extract generalized, reusable concept tags from literature chunks.

Steps:
  1. Load all text chunks from ULTIMATE_BOOK_DATA_03_04_translated.json
  2. Group them into LLM-sized batches
  3. Ask Bedrock Haiku to generate concept tags (SCREAMING_SNAKE_CASE)
  4. Deduplicate and normalize
  5. Output: concept_tags.json

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
import random
import re
from pathlib import Path
from typing import Any

from langchain_aws import ChatBedrock
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable
from pydantic import BaseModel

MODEL_ID = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
TOKENS_PER_CHAR = 1 / 4

DB_BRIEF_DESCRIPTION = """\
BeliefCraft is a warehouse simulation & analytics platform with PostgreSQL backend.
Core domains: logistics (warehouses, suppliers, routes, shipments), inventory
(products, locations, stock moves), procurement (purchase orders, suppliers),
and observability (sensor devices, noisy observations).
The agent uses this data for decision-making under uncertainty.\
"""


class TagList(BaseModel):
    tags: list[str]


class CanonicalTagList(BaseModel):
    tags: list[str]


_prompt = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are an expert at extracting high-level, reusable concept tags from technical "
            "documentation. These tags will power an autonomous logistics agent that reasons about "
            "algorithms, data, and constraints. Generate tags that are GENERAL enough to apply to "
            "multiple chunks across the book, but SPECIFIC enough to be useful for retrieval and "
            "agent reasoning.",
        ),
        (
            "human",
            """\
Batch of text chunks from "Algorithms for Decision Making":

DATABASE CONTEXT:
{db_description}

BATCH CONTENT:
{batch_content}

Generate generalized concept tags that:
1. Are REUSABLE — apply to multiple chunks/sections, not just this batch
2. Are ACTIONABLE — help an agent decide which algorithm/tool/constraint to use
3. Bridge domains: literature concepts ↔ warehouse data ↔ agent decisions
4. Follow format: SCREAMING_SNAKE_CASE, concise (e.g. STOCHASTIC_OPTIMIZATION)

Good: POMDP_BELIEF_UPDATE, LEADTIME_RISK_ASSESSMENT, INVENTORY_RECONCILIATION
Bad: chapter_7_intro (too specific), optimization (too vague), VERY_LONG_TAG_NAME_WITH_MANY_WORDS
""",
        ),
    ]
)

_semantic_dedup_prompt = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You normalize concept tags for retrieval systems. Remove semantically duplicate tags "
            "while preserving distinct concepts. Output only canonical tags that are already "
            "present in the input list and keep SCREAMING_SNAKE_CASE.",
        ),
        (
            "human",
            """\
Given this tag list, remove semantic duplicates (synonyms, near-duplicates, wording variants).
Return a reduced list of canonical tags.

Rules:
1. Keep only tags from the provided list (do not invent new tags)
2. Keep broad coverage; only merge truly overlapping concepts
3. Output format: SCREAMING_SNAKE_CASE

INPUT_TAGS:
{tags_text}
""",
        ),
    ]
)


def build_chain() -> Runnable[dict[str, Any], Any]:
    llm = ChatBedrock(
        model=MODEL_ID,
        model_kwargs={"max_tokens": 2048, "temperature": 0.3},
    )
    return _prompt | llm.with_structured_output(TagList).with_retry(stop_after_attempt=3)


def build_semantic_dedup_chain() -> Runnable[dict[str, Any], Any]:
    llm = ChatBedrock(
        model=MODEL_ID,
        model_kwargs={"max_tokens": 2048, "temperature": 0.0},
    )
    return _semantic_dedup_prompt | llm.with_structured_output(CanonicalTagList).with_retry(
        stop_after_attempt=3
    )


def normalize_tag(tag: str) -> str | None:
    tag = re.sub(r"[^A-Z0-9_]", "", tag.strip().upper().replace(" ", "_").replace("-", "_"))
    return tag if re.match(r"^[A-Z][A-Z0-9_]{2,}$", tag) else None


def deduplicate_tags(tags: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for tag in tags:
        t = normalize_tag(tag)
        if t and t not in seen:
            seen.add(t)
            result.append(t)
    return result


def semantic_deduplicate_tags(tags: list[str], chain: Runnable[dict[str, Any], Any]) -> list[str]:
    normalized = deduplicate_tags(tags)
    if not normalized:
        return []

    try:
        result: CanonicalTagList = chain.invoke({"tags_text": "\n".join(normalized)})
    except Exception:
        return normalized

    selected = deduplicate_tags(getattr(result, "tags", []))
    if not selected:
        return normalized

    allowed = set(normalized)
    selected_set = {tag for tag in selected if tag in allowed}
    if not selected_set:
        return normalized

    # Preserve deterministic order based on first occurrence in normalized tags.
    return [tag for tag in normalized if tag in selected_set]


def create_batches(
    chunks: list[dict[str, Any]], max_tokens: int, rng: random.Random
) -> list[list[dict[str, Any]]]:
    shuffled = chunks[:]
    rng.shuffle(shuffled)
    batches: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    current_tokens = 0
    for chunk in shuffled:
        cost = int(len(chunk["content"]) * TOKENS_PER_CHAR)
        if current and current_tokens + cost > max_tokens:
            batches.append(current)
            current, current_tokens = [], 0
        current.append(chunk)
        current_tokens += cost
    if current:
        batches.append(current)
    return batches


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Generate concept tags via LangChain + Bedrock.")
    p.add_argument("--input", type=Path, default=Path("ULTIMATE_BOOK_DATA_03_04_translated.json"))
    p.add_argument("--output", type=Path, default=Path("concept_tags.json"))
    p.add_argument("--tokens-per-batch", type=int, default=6000)
    p.add_argument("--seed", type=int, default=42)
    return p.parse_args()


def main() -> None:
    args = parse_args()

    print(f"Loading chunks from {args.input} ...")
    all_chunks: list[dict[str, Any]] = json.loads(args.input.read_text(encoding="utf-8"))
    chunks = [c for c in all_chunks if c.get("content", "").strip()]
    print(f"  Loaded {len(chunks)} chunks with content.")

    chain = build_chain()
    semantic_dedup_chain = build_semantic_dedup_chain()
    batches = create_batches(chunks, args.tokens_per_batch, random.Random(args.seed))  # noqa: S311
    print(f"  Batches: {len(batches)}")

    all_tags: list[str] = []
    for i, batch in enumerate(batches):
        print(f"  Batch {i + 1}/{len(batches)} ({len(batch)} chunks) ...", end=" ")
        try:
            result: TagList = chain.invoke(
                {
                    "db_description": DB_BRIEF_DESCRIPTION,
                    "batch_content": "\n\n---\n\n".join(
                        f"[Chunk {j + 1}] {c['content']}" for j, c in enumerate(batch)
                    ),
                }
            )
            tags = [t for t in (normalize_tag(tag) for tag in result.tags) if t]
            all_tags.extend(tags)
            print(f"OK ({len(tags)} tags)")
        except Exception as e:
            print(f"FAILED: {e}")

    unique_tags = semantic_deduplicate_tags(all_tags, semantic_dedup_chain)
    normalized_unique_count = len(deduplicate_tags(all_tags))
    print(
        f"\n  Raw: {len(all_tags)}, unique after normalization: {normalized_unique_count}, "
        f"unique after semantic dedup: {len(unique_tags)}"
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps({"tags": unique_tags}, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\nSaved {len(unique_tags)} tags → {args.output}")
    print("Sample:", unique_tags[:10])


if __name__ == "__main__":
    main()
