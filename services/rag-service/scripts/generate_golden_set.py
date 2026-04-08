"""
Golden Set Generator for RAG Retrieval Evaluation.

V2 (April 2026) — Single-Topic Strategy

Reads chunks from ULTIMATE_BOOK_DATA JSON file, applies stratified sampling by chunk_type,
partitions them into topic-coherent groups, then generates questions where answers come from
WITHIN each group only. This avoids cross-topic contamination that caused low recall in V1.

Key improvements:
- ✅ Single-topic questions (no forced cross-group pairing)
- ✅ Adaptive chunk limits (1-3 chunks per question)
- ✅ Stricter validation (no multiple exercise/example chunks)
- ✅ Better prompts (specific exclusion criteria)

Output: golden_set.json — committed as source of truth for regression testing.

Usage:
    uv run --project services/rag-service \\
        python services/rag-service/scripts/generate_golden_set.py \\
        --input ULTIMATE_BOOK_DATA_03_04_translated.json \\
        --output services/rag-service/tests/retrieval/golden_set.json \\
        --max-group-tokens 3000 \\
        --questions-per-type 6 \\
        --questions-per-group 3 \\
        --paraphrases-per-question 5 \\
        --seed 42

Reads OPENAI_API_KEY from services/rag-service/.env
"""

import argparse
import json
import os
import random
from collections import defaultdict
from pathlib import Path
from typing import Any, cast

from common.logging import configure_logging, get_logger
from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, Field

env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

logger = get_logger(__name__)

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.4-mini")
OPENAI_MAX_COMPLETION_TOKENS = 16384
OPENAI_TEMPERATURE = 0

# Chunk types for stratified sampling
CHUNK_TYPES = [
    "text",
    "formula",
    "table",
    "algorithm",
    "captioned_image",
    "exercise",
    "example",
]

_SYSTEM_PROMPT = (
    "You are an expert at creating HIGH-QUALITY retrieval evaluation datasets for the book "
    "'Algorithms for Decision Making'. You generate precise technical questions that can be "
    "answered using ONLY the provided chunks. You select STRICTLY MINIMAL sets of chunks (1-3) "
    "that are NECESSARY to answer each question. You avoid generic definitions, nearby context, "
    "and tangentially related material."
)

_USER_PROMPT_TEMPLATE = """\
You are given a group of related chunks from the book "Algorithms for Decision Making".
Each chunk is identified by its chunk_id.

CHUNKS:
{chunks}

Generate exactly {n_questions} technical questions such that:

1. Each question can be answered using ONLY chunks from this group (1-3 chunks per question).
2. DO NOT create questions requiring information not present in these chunks.
3. For each question, list the chunk_ids of the MINIMUM set of chunks needed to answer it.

⚠️ CRITICAL RULE FOR MULTI-CHUNK QUESTIONS:

   Use 2-3 chunks ONLY when they are SEMANTICALLY VERY CLOSE:
   ✅ GOOD multi-chunk examples:
      - Algorithm description + same algorithm's complexity analysis
      - Formula definition + example using that same formula
      - Theory section + direct application of that theory
      - Step 1 of process + Step 2 of SAME process

   ❌ BAD multi-chunk examples (will fail semantic search):
      - Different algorithms (e.g., particle filter + Kalman filter)
      - Different exercises (e.g., Exercise 7.4 + Exercise 13.2)
      - Unrelated concepts that happen to be in same group
      - Comparing method A vs method B (semantic search can't find both)

📊 TARGET DISTRIBUTION:
   - 40% simple (1 chunk): Definitions, single-concept explanations
   - 40% medium (2 chunks): Tightly coupled concepts (algorithm + its analysis)
   - 20% complex (3 chunks): Multi-step processes from same workflow

   PREFER 1-CHUNK QUESTIONS when chunks are not tightly semantically related!

CRITICAL RULES FOR relevant_ids:

✅ INCLUDE only chunks that:
  - Contain the DIRECT answer (algorithms, formulas, specific methods, definitions)
  - Provide ESSENTIAL context without which the question cannot be answered
  - Each contribute UNIQUE necessary information

❌ EXCLUDE these types:
  - Generic definitions when question asks about specific algorithms
  - Nearby context that was adjacent in book but not essential
  - Exercise chunks when question asks for theory/explanation
  - Background information that provides context but not the answer
  - Duplicate information already in other selected chunks

🎯 MATCH QUESTION STYLE TO CHUNK TYPE:

   When expected chunk is **algorithm_*** (pseudocode/implementation):
   ✅ MUST include specific algorithm/method name
      (e.g., ParticleFilter.update, VariableElimination.infer)
   ✅ Ask about: "What steps does [MethodName]...", "How does [AlgorithmName] procedure..."
   ❌ NEVER use generic: "the algorithm", "particle filter update", "the method"
      without specific name
     - "What steps does the ParticleFilter.update method use to transform states?"
     - "How does the VariableElimination.infer procedure combine conditioned factors?"

   BAD Examples (will match text explanations instead):
     - "How does particle filter update work?" (no method name → finds text)
     - "In the update, how are states sampled?" (generic "the update" → finds text)
     - "Given a belief, how does the algorithm decide?" (no algorithm name → finds text)

   When expected chunk is **exercise_*** or **formula_*** (mathematical):
   ✅ Ask about: specific formulas, equations, "compute X given Y", "what is the equation for"
   ❌ Avoid: vague "how are X and Y related" (too general, finds text explanations)
   Example: "What is the formula for computing U(s) from Q(s,a) values?"

   When expected chunk is **text_*** (conceptual):
   ✅ Ask about: concepts, relationships, "what is", "why", "how does X relate to Y"
   ❌ Avoid: technical "procedure", "steps", "algorithm" (finds algorithm chunks instead)
   ❌ Avoid: formula notation questions (finds numbered_formula chunks instead)
   Example: "Why do particle filters lose diversity over time?"

⚠️ AVOID SPECIFIC REFERENCES:
  - DO NOT mention "Exercise X.Y" or "Example X.Y" unless the chunk explicitly contains that number
  - DO NOT reference algorithm names not present in the chunks
  - DO NOT reference code fields/methods (e.g., ".TR field") not in the chunks
  - Use GENERIC terminology when possible (e.g., "action-value functions" instead of "Exercise 7.4")

EXAMPLES:

❌ BAD — Generic algorithm reference without method name:
   Chunk: algorithm_3f8d0031 (ParticleFilter.update code)
   Question: "In the particle filter update, how are next states sampled, weighted, and resampled?"
   Problem: No method name! "particle filter update" matches TEXT explanations
            better than algorithm code.

✅ GOOD — Specific method name:
   Chunk: algorithm_3f8d0031 (ParticleFilter.update code)
   Question: "What steps does the ParticleFilter.update method perform to transform state samples?"
   Why: Contains "ParticleFilter.update" → retrieval finds algorithm chunk, not text

❌ BAD — Wrong question style for algorithm chunk:
   Chunk: algorithm_3f8d0031 (ParticleFilter.update code)
   Question: "What is the purpose of particle filter belief updates?"
   Problem: Conceptual question finds TEXT explanations, not algorithm code!

❌ BAD — Wrong question style for exercise/formula chunk:
   Chunk: exercise_xyz123 (Q-values, U(s), π(s) formulas)
   Question: "How are state utility, greedy policy, and advantage related?"
   Problem: Vague conceptual question finds text explanations, not formulas!

✅ GOOD — Correct question style for exercise/formula chunk:
   Chunk: exercise_xyz123 (Q-values, U(s), π(s) formulas)
   Question: "What are the exact formulas for computing U(s) and π(s) from Q(s,a)?"
   Why: Asks for specific formulas → finds exercise/formula chunk

❌ BAD — Too specific reference:
   Question: "Using the Q-values from Exercise 7.4, compute U(s) and π(s)"
   Problem: References specific exercise not in all chunks

✅ GOOD — Generic terminology:
   Question: "How do action-value functions relate to state utility and greedy policy?"
   Why: Generic terminology, answerable from chunks without specific references

❌ BAD — Multiple unrelated chunks:
   relevant_ids: [algorithm_particle_filter, algorithm_kalman_filter]
   Problem: Semantic search cannot find both different algorithms simultaneously

✅ GOOD — Single topic:
   relevant_ids: [text_bellman_equation, text_policy_evaluation]
   Why: Both from same topic, semantically related

4. For each question, generate exactly {n_paraphrases} paraphrase variants that:
   - Preserve the exact semantic meaning
   - Use different wording, synonyms, or sentence structure
   - Are answerable from the same chunks
"""


class GeneratedQuestion(BaseModel):
    """A single generated retrieval question with paraphrases and relevant chunk IDs."""

    question: str
    paraphrases: list[str] = Field(min_length=1)
    relevant_ids: list[str] = Field(
        min_length=1,
        max_length=3,
        description="Chunk IDs that are STRICTLY NECESSARY to answer the question. "
        "Use 1 chunk for simple questions, 2-3 chunks ONLY when they are semantically very close "
        "(e.g., algorithm + its explanation, formula + example, NOT different algorithms).",
    )


class GeneratedBatch(BaseModel):
    """Batch of generated questions for one group pair."""

    questions: list[GeneratedQuestion]


def load_chunks_from_json(json_path: Path) -> list[dict[str, Any]]:
    """Load all chunks from JSON file."""
    with json_path.open("r", encoding="utf-8") as f:
        chunks: list[dict[str, Any]] = json.load(f)
    logger.info("chunks_loaded", total=len(chunks), source=str(json_path))
    return chunks


def stratified_sample_by_type(
    chunks: list[dict[str, Any]], questions_per_type: int, rng: random.Random
) -> list[dict[str, Any]]:
    """Sample chunks using stratified sampling by chunk_type.

    For each chunk_type, randomly sample up to questions_per_type * 2 chunks.
    This ensures diverse coverage across different content types (text, formula, table, etc.).
    """
    by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for chunk in chunks:
        chunk_type = chunk.get("chunk_type", "text")
        by_type[chunk_type].append(chunk)

    sampled: list[dict[str, Any]] = []
    for chunk_type in CHUNK_TYPES:
        type_chunks = by_type.get(chunk_type, [])
        if not type_chunks:
            logger.warning("no_chunks_for_type", chunk_type=chunk_type)
            continue

        # Sample 2 chunks per desired question to ensure enough material for pairs
        sample_size = min(len(type_chunks), questions_per_type * 2)
        sampled.extend(rng.sample(type_chunks, sample_size))

    logger.info(
        "stratified_sampling_complete",
        total_sampled=len(sampled),
        questions_per_type=questions_per_type,
    )
    return sampled


def partition_into_groups(
    chunks: list[dict[str, Any]], max_group_tokens: int
) -> list[list[dict[str, Any]]]:
    """Split chunks into groups whose combined content fits max_group_tokens.

    Uses a characters-to-tokens approximation of 4 chars ≈ 1 token.
    """
    groups: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    current_tokens = 0

    for chunk in chunks:
        content = chunk.get("content", "")
        chunk_tokens = len(content) // 4
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


def select_groups_for_generation(
    groups: list[list[dict[str, Any]]], max_groups: int, rng: random.Random
) -> list[list[dict[str, Any]]]:
    """Select up to max_groups for question generation.

    Shuffles groups deterministically and selects the first max_groups.
    This ensures diverse coverage across the dataset.
    """
    shuffled_indices = list(range(len(groups)))
    rng.shuffle(shuffled_indices)

    selected = [groups[i] for i in shuffled_indices[:max_groups]]

    logger.info(
        "groups_selected",
        total_available=len(groups),
        selected=len(selected),
    )
    return selected


def format_group_for_prompt(group: list[dict[str, Any]]) -> str:
    """Render a group of chunks as labelled text for the LLM prompt."""
    lines = []
    for chunk in group:
        chunk_id = chunk.get("chunk_id", "unknown")
        content = chunk.get("content", "")
        lines.append(f"[chunk_id: {chunk_id}]\n{content}\n")
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

    return cast(list[dict[str, Any]], [q.model_dump() for q in batch.questions])


def generate_questions_for_group(
    openai_client: OpenAI,
    group: list[dict[str, Any]],
    chunk_id_to_pdf_blocks: dict[str, list[str]],
    n_questions: int,
    n_paraphrases: int,
    group_index: int,
) -> list[dict[str, Any]]:
    """Call OpenAI to generate single-topic questions for one group of chunks."""
    prompt = _USER_PROMPT_TEMPLATE.format(
        chunks=format_group_for_prompt(group),
        n_questions=n_questions,
        n_paraphrases=n_paraphrases,
    )

    try:
        questions = call_openai_structured(openai_client, prompt, n_questions, n_paraphrases)
        # Enrich with expected_chunks structure (chunk_id + pdf_block_ids)
        for q in questions:
            q["expected_chunks"] = [
                {
                    "chunk_id": chunk_id,
                    "pdf_block_ids": chunk_id_to_pdf_blocks.get(chunk_id, []),
                }
                for chunk_id in q.get("relevant_ids", [])
            ]
        logger.info("group_generated", group=group_index, questions=len(questions))
        return questions
    except Exception as exc:
        logger.error("group_generation_failed", group=group_index, error=str(exc))
        return []


def validate_question_chunk_relevance(
    question: str,
    expected_chunk_ids: list[str],
    chunks_by_id: dict[str, dict[str, Any]],
) -> tuple[bool, str]:
    """
    Validate that expected chunks actually contain entities mentioned in the question.

    Returns (is_valid, reason).

    Checks:
    1. NO multiple exercise/example chunks (they reference different parts of book)
    2. Exercise/example chunks MUST be explicitly referenced in question
    3. Algorithm chunks MUST use procedural language or algorithm name
    4. Exercise/example references in question must appear in expected chunks
    5. Specific technical terms with parentheses (e.g., "TR(s,a)") appear in chunks
    6. Code field/method references (e.g., ".TR field") appear in chunks
    """
    import re

    # Get content of all expected chunks (used by multiple rules below)
    chunk_contents = []
    chunk_contents_original = []
    for chunk_id in expected_chunk_ids:
        chunk = chunks_by_id.get(chunk_id)
        if chunk:
            content = chunk.get("content", "")
            chunk_contents.append(content.lower())
            chunk_contents_original.append(content)

    combined_content = " ".join(chunk_contents)
    combined_content_original = " ".join(chunk_contents_original)

    # STRICT RULE 1: Reject questions with 2+ exercise or example chunks
    # These almost always fail because they reference different specific problems
    exercise_example_chunks = [
        cid
        for cid in expected_chunk_ids
        if cid.startswith("exercise_") or cid.startswith("example_")
    ]
    if len(exercise_example_chunks) >= 2:
        return (
            False,
            f"Question has {len(exercise_example_chunks)} exercise/example chunks - "
            "semantic search can't find both simultaneously",
        )

    # STRICT RULE 2: Reject questions with 2+ algorithm chunks
    # Different algorithms are rarely retrieved together by semantic search
    algorithm_chunks = [cid for cid in expected_chunk_ids if cid.startswith("algorithm_")]
    if len(algorithm_chunks) >= 2:
        return (
            False,
            f"Question has {len(algorithm_chunks)} algorithm chunks - "
            "different algorithms rarely retrieved together",
        )

    # STRICT RULE 3: Exercise/example chunks MUST be explicitly referenced
    # Abstract questions like "What are the formulas for..." fail to retrieve specific exercises
    # Also accept "in the example" or "in Exercise X.Y"
    if (
        exercise_example_chunks
        and not re.search(r"\b(Exercise|Example)\s+\d+\.\d+", question, re.IGNORECASE)
        and not re.search(r"\bin\s+the\s+(example|exercise)", question, re.IGNORECASE)
    ):
        return (
            False,
            "Exercise/example chunks must be explicitly referenced by number "
            "(e.g., 'Exercise 7.4') or 'in the example'",
        )

    # STRICT RULE 4: Algorithm chunks MUST use procedural language AND algorithm/method name
    # Generic "the algorithm" or "particle filter update" questions match TEXT explanations
    # instead of ALGORITHM pseudocode — REQUIRE specific names like "ParticleFilter.update"
    if algorithm_chunks:
        # Extract potential algorithm/method names from chunks (CamelCase.method or function_name)
        algo_names = set()

        # CamelCase class names and methods (e.g., ParticleFilter, VariableElimination.infer)
        for match in re.findall(
            r"\b([A-Z][a-z]+(?:[A-Z][a-z]+)+)(?:\.([a-z_]+))?", combined_content_original
        ):
            class_name = match[0]
            method_name = match[1]
            if len(class_name) > 3:
                algo_names.add(class_name)
            if method_name and len(method_name) > 2:
                algo_names.add(f"{class_name}.{method_name}")

        # Function names (e.g., particle_filter_update, variable_elimination)
        algo_names.update(
            match
            for match in re.findall(r"\b([a-z_]+_[a-z_]+)\s*\(", combined_content_original)
            if len(match) > 5
        )

        # Check if ANY algorithm/method name appears in question
        has_algo_name = any(name.lower() in question.lower() for name in algo_names)

        if not has_algo_name:
            return (
                False,
                f"Algorithm chunks REQUIRE specific algorithm/method name in question "
                f"(e.g., {', '.join(list(algo_names)[:3])}...) - "
                "generic 'the algorithm' or 'particle filter' matches text explanations instead",
            )

    # STRICT RULE 5: Reject formula-focused questions when expected chunk is text type
    # Questions like "How is X expressed?" match numbered_formula chunks better than text chunks
    # that contain the same formula + explanation
    if expected_chunk_ids:
        # Check if all expected chunks are text type (not numbered_formula)
        text_only_chunks = all(
            not cid.startswith("numbered_formula_") for cid in expected_chunk_ids
        )

        if text_only_chunks:
            # Indicators of formula-focused questions
            formula_focus_patterns = [
                r"\b(expressed|written|formulated|represented)\s+(as|in|recursively)\b",
                r"\b(equation|formula|expression)\s+(form|notation|is)\b",
                r"\b(linear\s+system|matrix\s+(form|equation|notation))\b",
                r"\b(recursive\s+(form|equation|expression))\b",
                r"\bhow\s+(is|are|do)\s+.*\s+(expressed|written|formulated|represented)\b",
            ]

            # Check if question contains mathematical notation (LaTeX, Greek letters)
            has_math_notation = bool(re.search(r"[\\^_{}]|\\[a-zA-Z]+|[αβγδεπθλμσΣ∑∏]", question))

            # Check if formula-focused language appears
            is_formula_focused = any(
                re.search(pattern, question, re.IGNORECASE) for pattern in formula_focus_patterns
            )

            if is_formula_focused or has_math_notation:
                return (
                    False,
                    "Formula-focused questions (notation/structure) are rejected for text chunks - "
                    "numbered_formula chunks will rank higher despite text having explanation",
                )

    # Extract specific references from question
    # Match both "Exercise X.Y" and "Example X.Y"
    exercise_pattern = r"(?:Exercise|Example)\s+(\d+\.\d+)"
    exercise_refs = re.findall(exercise_pattern, question, re.IGNORECASE)

    # Extract technical terms with parentheses (likely function/method names)
    tech_term_pattern = r"\b([A-Z][A-Za-z_]*\([^)]*\))"
    tech_terms = re.findall(tech_term_pattern, question)

    # Extract code field references (.field_name)
    field_pattern = r"\.([A-Z_]+)\s+field"
    field_refs = re.findall(field_pattern, question)

    # Validate exercise/example references
    if exercise_refs:
        for ex_ref in exercise_refs:
            # Check if any chunk contains this number
            if ex_ref not in combined_content:
                return (
                    False,
                    f"Question mentions number '{ex_ref}' but no expected chunk contains it",
                )

    # Validate technical terms (lenient - just check if prefix exists)
    if tech_terms:
        for term in tech_terms:
            func_name = term.split("(")[0]
            if func_name.lower() not in combined_content:
                return False, f"Question mentions '{term}' but term not found in expected chunks"

    # Validate field references
    if field_refs:
        for field in field_refs:
            if field.lower() not in combined_content:
                return False, f"Question mentions '.{field} field' but not found in expected chunks"

    return True, "OK"


def assign_split(rng: random.Random) -> str:
    """Assign a dataset split: 80% validation, 20% test."""
    return "validation" if rng.random() < 0.8 else "test"


def build_golden_set_entry(
    case_id: str,
    question_data: dict[str, Any],
    split: str,
) -> dict[str, Any]:
    """Convert raw LLM question output to a golden set entry with expected_chunks."""
    return {
        "id": case_id,
        "question": question_data["question"],
        "paraphrases": question_data.get("paraphrases", []),
        "expected_chunks": question_data.get("expected_chunks", []),
        "split": split,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate golden set for RAG retrieval evaluation from JSON chunks."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("ULTIMATE_BOOK_DATA_03_04_translated.json"),
        help="Input JSON file with chunks (default: ULTIMATE_BOOK_DATA_03_04_translated.json)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("services/rag-service/tests/retrieval/golden_set.json"),
        help="Output path for golden_set.json",
    )
    parser.add_argument(
        "--max-group-tokens",
        type=int,
        default=150_000,
        help="Max tokens per chunk group (default: 150000)",
    )
    parser.add_argument(
        "--questions-per-type",
        type=int,
        default=3,
        help="Questions to generate per chunk_type via stratified sampling (default: 3)",
    )
    parser.add_argument(
        "--questions-per-group",
        type=int,
        default=3,
        help="Questions to generate per group (default: 3)",
    )
    parser.add_argument(
        "--max-groups",
        type=int,
        default=None,
        help="Maximum number of groups to use (default: all groups)",
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

    # Load chunks from JSON file
    if not args.input.exists():
        logger.error("input_file_not_found", path=str(args.input))
        raise SystemExit(1)

    try:
        all_chunks = load_chunks_from_json(args.input)
    except Exception as exc:
        logger.error("json_load_failed", path=str(args.input), error=str(exc))
        raise SystemExit(1) from exc

    if not all_chunks:
        logger.error("no_chunks_found", path=str(args.input))
        raise SystemExit(1)

    # Build chunk_id -> pdf_block_ids mapping
    chunk_id_to_pdf_blocks = {
        chunk["chunk_id"]: chunk.get("pdf_block_ids", [])
        for chunk in all_chunks
        if "chunk_id" in chunk
    }

    # Build chunk_id -> chunk mapping for validation
    chunks_by_id = {chunk["chunk_id"]: chunk for chunk in all_chunks if "chunk_id" in chunk}

    # Stratified sampling by chunk_type
    sampled_chunks = stratified_sample_by_type(all_chunks, args.questions_per_type, rng)
    if not sampled_chunks:
        logger.error("stratified_sampling_failed")
        raise SystemExit(1)

    # Partition into groups
    groups = partition_into_groups(sampled_chunks, args.max_group_tokens)
    if len(groups) < 1:
        logger.error("not_enough_groups", groups=len(groups))
        raise SystemExit(1)

    # Select groups for generation
    max_groups = args.max_groups if args.max_groups else len(groups)
    selected_groups = select_groups_for_generation(groups, max_groups, rng)

    if not args.openai_api_key:
        logger.error(
            "missing_openai_api_key",
            advice="Set OPENAI_API_KEY env var or pass --openai-api-key",
        )
        raise SystemExit(1)

    openai_client = OpenAI(api_key=args.openai_api_key)

    entries: list[dict[str, Any]] = []
    case_counter = 1
    filtered_count = 0

    for group_idx, group in enumerate(selected_groups):
        questions = generate_questions_for_group(
            openai_client,
            group,
            chunk_id_to_pdf_blocks,
            args.questions_per_group,
            args.paraphrases_per_question,
            group_index=group_idx,
        )
        for q in questions:
            # Validate that expected chunks contain entities mentioned in question
            is_valid, reason = validate_question_chunk_relevance(
                question=q["question"],
                expected_chunk_ids=q.get("relevant_ids", []),
                chunks_by_id=chunks_by_id,
            )

            if not is_valid:
                filtered_count += 1
                logger.warning(
                    "question_filtered",
                    group=group_idx,
                    reason=reason,
                    question=q["question"][:100] + "...",
                )
                continue

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
        filtered=filtered_count,
        validation=validation_count,
        test=test_count,
    )

    if len(entries) < 15:
        logger.warning(
            "below_minimum_threshold",
            generated=len(entries),
            minimum=15,
            advice="Increase --questions-per-type or --questions-per-group or --max-groups",
        )


if __name__ == "__main__":
    main()
