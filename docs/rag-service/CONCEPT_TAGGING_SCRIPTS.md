# Concept Tagging Scripts

This note describes two RAG data-enrichment scripts in `services/rag-service/src/rag_scripts`.

## 1) `concept_tags_generator.py`

Generates a reusable concept tag vocabulary from chunk text.

- **Input**: chunk JSON (default: `ULTIMATE_BOOK_DATA_03_04_translated.json`)
- **Output**: `concept_tags.json` with shape:
  - `{"tags": ["TAG_ONE", "TAG_TWO", ...]}`
- **What it does**:
  1. Loads chunks with non-empty `content`
  2. Batches text by token budget
  3. Calls AWS Bedrock Haiku to propose generalized tags
  4. Normalizes + deduplicates tags

Run example:

```bash
python services/rag-service/src/rag_scripts/concept_tags_generator.py \
  --input services/rag-service/src/rag_scripts/ULTIMATE_BOOK_DATA_03_04_translated.json \
  --output services/rag-service/src/rag_scripts/concept_tags.json \
  --tokens-per-batch 6000 \
  --seed 42
```

## 2) `concept_mapping.py`

Enriches chunks with BeliefCraft concept tags and DB table tags.

- **Inputs**:
  - chunk JSON (`--input`)
  - generated concept tag list (`--tags-input`)
- **Outputs**:
  - concepts JSONL (`--concepts`) with `bc_concepts`
  - tables JSONL (`--tables`) with `bc_db_tables`
  - merged enriched JSON (`--output`)
- **What it does**:
  1. Tags each chunk with `bc_concepts` (resumable)
  2. Tags each chunk with `bc_db_tables` (resumable)
  3. Merges tags back into one enriched chunk file

Run example:

```bash
python services/rag-service/src/rag_scripts/concept_mapping.py \
  --input services/rag-service/src/rag_scripts/ULTIMATE_BOOK_DATA_03_04_translated.json \
  --tags-input services/rag-service/src/rag_scripts/concept_tags.json \
  --concepts services/rag-service/src/rag_scripts/chunk_concepts.jsonl \
  --tables services/rag-service/src/rag_scripts/chunk_bc_tables.jsonl \
  --output services/rag-service/src/rag_scripts/ULTIMATE_BOOK_DATA_enriched.json
```

## Requirements

Both scripts use AWS Bedrock (`boto3`) and expect valid AWS credentials/region in the environment or AWS config files.
