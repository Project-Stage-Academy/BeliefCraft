"""
Golden Set Generator for RAG Retrieval Evaluation.

Fetches all chunks from Weaviate, partitions them into groups,
then iterates over ALL distinct group pairs (round-robin, deterministic)
and uses OpenAI with Pydantic-enforced structured output to generate
retrieval evaluation questions with paraphrases.

Output: golden_set.json — committed as source of truth for regression testing.

Usage:
    uv run --project services/rag-service \\
        python services/rag-service/scripts/generate_golden_set.py \\
        --output services/rag-service/tests/retrieval/golden_set.json \\
        --max-group-tokens 150000 \\
        --pairs-count 10 \\
        --questions-per-pair 3 \\
        --paraphrases-per-question 5 \\
        --seed 42

Reads OPENAI_API_KEY from services/rag-service/.env
"""

import argparse
import json
import os
import random
from itertools import combinations, cycle
from pathlib import Path
from typing import Any

import weaviate
from common.logging import configure_logging, get_logger
from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, Field
from rag_service.constants import COLLECTION_NAME

env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

logger = get_logger(__name__)

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_MAX_COMPLETION_TOKENS = 16384
OPENAI_TEMPERATURE = 0.3

_SYSTEM_PROMPT = (
    "You are an expert at creating retrieval evaluation datasets for the book "
    "'Algorithms for Decision Making'. You generate precise technical questions "
    "whose answers require combining information from multiple text passages."
)

_USER_PROMPT_TEMPLATE = """\
You are given two groups of text chunks from the book "Algorithms for Decision Making".
Each chunk is identified by its Weaviate UUID.

GROUP A:
{group_a}

GROUP B:
{group_b}

Generate exactly {n_questions} technical questions such that:
1. Each correct answer REQUIRES retrieving chunks from BOTH groups simultaneously.
2. Questions must be non-obvious — not answerable from a single chunk alone.
3. For each question, list the UUIDs of ALL relevant chunks (minimum one from each group).
4. For each question, generate exactly {n_paraphrases} paraphrase variants that:
   - Preserve the exact semantic meaning of the original question.
   - Use different wording, synonyms, or sentence structure.
   - Have the same relevant chunks as the original question.
"""


class GeneratedQuestion(BaseModel):
    """A single generated retrieval question with paraphrases and relevant chunk IDs."""

    question: str
    paraphrases: list[str] = Field(min_length=1)
    relevant_ids: list[str] = Field(min_length=2)


class GeneratedBatch(BaseModel):
    """Batch of generated questions for one group pair."""

    questions: list[GeneratedQuestion]


def fetch_all_chunks(client: weaviate.WeaviateClient) -> list[dict[str, str]]:
    """Retrieve all chunks from Weaviate, returning only uuid and content fields."""
    collection = client.collections.use(COLLECTION_NAME)
    chunks: list[dict[str, str]] = []
    for obj in collection.iterator(return_properties=["content"]):
        content = str(obj.properties.get("content") or "")
        chunks.append({"uuid": str(obj.uuid), "content": content})
    chunks.sort(key=lambda c: c["uuid"])
    logger.info("chunks_fetched", total=len(chunks))
    return chunks


def partition_into_groups(
    chunks: list[dict[str, str]], max_group_tokens: int
) -> list[list[dict[str, str]]]:
    """Split sorted chunks into groups whose combined content fits max_group_tokens.

    Uses a characters-to-tokens approximation of 4 chars ≈ 1 token.
    """
    groups: list[list[dict[str, str]]] = []
    current: list[dict[str, str]] = []
    current_tokens = 0

    for chunk in chunks:
        chunk_tokens = len(chunk["content"]) // 4
        if current and current_tokens + chunk_tokens > max_group_tokens:
            groups.append(current)
            current = []
            current_tokens = 0
        current.append(chunk)
        current_tokens += chunk_tokens

    if current:
        groups.append(current)

    logger.info("groups_created", total=len(groups))
    return groups


def schedule_pair_iterations(
    groups: list[list[dict[str, str]]], pairs_count: int, rng: random.Random
) -> list[tuple[list[dict[str, str]], list[dict[str, str]]]]:
    """Return exactly pairs_count (group_a, group_b) pairs.

    Enumerates all unique group pairs, shuffles them once (deterministic via seed),
    then cycles through the full list until pairs_count is reached.
    This guarantees every pair appears at least floor(pairs_count/total_pairs) times
    before any pair repeats — full coverage before any repetition.
    """
    all_pairs = list(combinations(range(len(groups)), 2))
    rng.shuffle(all_pairs)

    scheduled: list[tuple[list[dict[str, str]], list[dict[str, str]]]] = []
    for idx, (i, j) in enumerate(cycle(all_pairs)):
        if idx >= pairs_count:
            break
        scheduled.append((groups[i], groups[j]))

    logger.info(
        "pairs_scheduled",
        total_unique=len(all_pairs),
        scheduled=len(scheduled),
    )
    return scheduled


def format_group_for_prompt(group: list[dict[str, str]]) -> str:
    """Render a group of chunks as labelled text for the LLM prompt."""
    lines = []
    for chunk in group:
        lines.append(f"[UUID: {chunk['uuid']}]\n{chunk['content']}\n")
    return "\n".join(lines)


def call_openai_structured(
    openai_client: OpenAI,
    prompt: str,
    n_questions: int,
    n_paraphrases: int,
) -> list[dict[str, Any]]:
    """Send a prompt to OpenAI and return validated structured question data."""
    response = openai_client.beta.chat.completions.parse(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        max_completion_tokens=OPENAI_MAX_COMPLETION_TOKENS,
        temperature=OPENAI_TEMPERATURE,
        response_format=GeneratedBatch,
    )
    batch = response.choices[0].message.parsed
    if batch is None:
        return []

    n_generated = len(batch.questions)
    if n_generated != n_questions:
        logger.warning(
            "question_count_mismatch",
            expected=n_questions,
            received=n_generated,
        )

    return [q.model_dump() for q in batch.questions]


def generate_questions_for_pair(
    openai_client: OpenAI,
    group_a: list[dict[str, str]],
    group_b: list[dict[str, str]],
    n_questions: int,
    n_paraphrases: int,
    pair_index: int,
) -> list[dict[str, Any]]:
    """Call OpenAI to generate cross-group questions for one pair of groups."""
    prompt = _USER_PROMPT_TEMPLATE.format(
        group_a=format_group_for_prompt(group_a),
        group_b=format_group_for_prompt(group_b),
        n_questions=n_questions,
        n_paraphrases=n_paraphrases,
    )

    try:
        questions = call_openai_structured(openai_client, prompt, n_questions, n_paraphrases)
        logger.info("pair_generated", pair=pair_index, questions=len(questions))
        return questions
    except Exception as exc:
        logger.error("pair_generation_failed", pair=pair_index, error=str(exc))
        return []


def assign_split(rng: random.Random) -> str:
    """Assign a dataset split: 80% validation, 20% test."""
    return "validation" if rng.random() < 0.8 else "test"


def build_golden_set_entry(
    case_id: str,
    question_data: dict[str, Any],
    split: str,
) -> dict[str, Any]:
    """Convert raw LLM question output to a golden set entry."""
    return {
        "id": case_id,
        "question": question_data["question"],
        "paraphrases": question_data.get("paraphrases", []),
        "expected_chunk_ids": question_data.get("relevant_ids", []),
        "split": split,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate golden set for RAG retrieval evaluation."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("services/rag-service/tests/retrieval/golden_set.json"),
        help="Output path for golden_set.json",
    )
    parser.add_argument(
        "--weaviate-host",
        default=os.getenv("WEAVIATE_HOST", "localhost"),
        help="Weaviate host (default: localhost)",
    )
    parser.add_argument(
        "--weaviate-port",
        type=int,
        default=int(os.getenv("WEAVIATE_PORT", "8080")),
        help="Weaviate HTTP port (default: 8080)",
    )
    parser.add_argument(
        "--max-group-tokens",
        type=int,
        default=150_000,
        help="Max tokens per chunk group (default: 150000)",
    )
    parser.add_argument(
        "--pairs-count",
        type=int,
        default=10,
        help="Number of pair iterations to schedule (default: 10)",
    )
    parser.add_argument(
        "--questions-per-pair",
        type=int,
        default=3,
        help="Questions to generate per pair (default: 3)",
    )
    parser.add_argument(
        "--paraphrases-per-question",
        type=int,
        default=5,
        help="Paraphrase variants per question (default: 5)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducibility (default: 42)",
    )
    parser.add_argument(
        "--openai-api-key",
        default=os.getenv("OPENAI_API_KEY"),
        help="OpenAI API key (default: OPENAI_API_KEY env var)",
    )
    return parser.parse_args()


def main() -> None:
    configure_logging("generate-golden-set")
    args = parse_args()
    rng = random.Random(args.seed)  # noqa: S311

    try:
        with weaviate.connect_to_local(
            host=args.weaviate_host, port=args.weaviate_port
        ) as weaviate_client:
            chunks = fetch_all_chunks(weaviate_client)
    except Exception as exc:
        logger.error("weaviate_connection_failed", error=str(exc))
        raise SystemExit(1) from exc

    if not chunks:
        logger.error("no_chunks_found", collection=COLLECTION_NAME)
        raise SystemExit(1)

    groups = partition_into_groups(chunks, args.max_group_tokens)
    if len(groups) < 2:
        logger.error("not_enough_groups", groups=len(groups))
        raise SystemExit(1)

    pairs = schedule_pair_iterations(groups, args.pairs_count, rng)

    if not args.openai_api_key:
        logger.error(
            "missing_openai_api_key",
            advice="Set OPENAI_API_KEY env var or pass --openai-api-key",
        )
        raise SystemExit(1)

    openai_client = OpenAI(api_key=args.openai_api_key)

    entries: list[dict[str, Any]] = []
    case_counter = 1

    for pair_idx, (group_a, group_b) in enumerate(pairs):
        questions = generate_questions_for_pair(
            openai_client,
            group_a,
            group_b,
            args.questions_per_pair,
            args.paraphrases_per_question,
            pair_index=pair_idx,
        )
        for q in questions:
            case_id = f"tc_{case_counter:03d}"
            split = assign_split(rng)
            entries.append(build_golden_set_entry(case_id, q, split))
            case_counter += 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)

    validation_count = sum(1 for e in entries if e["split"] == "validation")
    test_count = sum(1 for e in entries if e["split"] == "test")
    logger.info(
        "golden_set_written",
        path=str(args.output),
        total=len(entries),
        validation=validation_count,
        test=test_count,
    )

    if len(entries) < 15:
        logger.warning(
            "below_minimum_threshold",
            generated=len(entries),
            minimum=15,
            advice="Run with more --pairs-count or check Weaviate data.",
        )


if __name__ == "__main__":
    main()
