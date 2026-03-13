# RAG Metadata Contract for Agent Extractors

## Purpose

This document defines the metadata fields currently consumed by `agent-service`
post-processing extractors.

If RAG metadata changes, keep this contract updated together with:

- `services/agent-service/app/services/extractors/citation_extractor.py`
- `services/agent-service/app/services/extractors/formula_extractor.py`
- `services/agent-service/app/services/extractors/code_extractor.py`
- `services/agent-service/app/services/extractors/tool_result_utils.py`

## Document Envelope Contract

`agent-service` expects RAG tool results to contain document objects that can be
normalized into this shape:

```json
{
  "id": "chunk_0001",
  "content": "chunk text",
  "metadata": {
    "...": "..."
  }
}
```

Supported result envelopes:

- `documents`
- `results`
- `expanded`
- `document` (single document)

## Required Fields

Minimal required fields for reliable extraction:

- `document.id`
- `document.content`
- `metadata.chunk_type`

## Citation Extractor Fields

File: `services/agent-service/app/services/extractors/citation_extractor.py`

Used fields:

- `metadata.chunk_type` (entity type resolution)
- `metadata.entity_id` (numbered entity identifier)
- `metadata.page` (preferred) or `metadata.page_number`
- `metadata.part_title`
- `metadata.section_title`
- `metadata.subsection_title`
- `metadata.subsubsection_title`

Fallbacks:

- `tool_arguments.entity_type`
- `tool_arguments.number` (for direct `get_entity_by_number`)

## Formula Extractor Fields

File: `services/agent-service/app/services/extractors/formula_extractor.py`

Used fields:

- `metadata.chunk_type` or `metadata.type`
- `metadata.description` (optional)
- `content` (formula text / LaTeX source)

Formula chunk types consumed:

- `formula`
- `numbered_formula`

## Code Extractor Fields

File: `services/agent-service/app/services/extractors/code_extractor.py`

Used fields:

- `metadata.chunk_type` or `metadata.type`
- `metadata.section_title` (description fallback)
- `metadata.subsection_title` (description fallback)
- `metadata.subsubsection_title` (description fallback)
- `content` (algorithm code body)

Code chunk types consumed:

- `algorithm`

Dependency metadata consumed (preferred):

- `metadata.declarations`
- `metadata.used_structs`
- `metadata.used_functions`

Legacy dependency compatibility (optional fallback):

- `metadata.dependencies`
- `metadata.python_dependencies`
- `metadata.required_packages`

## Normalization / Alias Rules

File: `services/agent-service/app/services/extractors/tool_result_utils.py`

Current alias support:

- `chunk_type=algorithm_code` -> `algorithm`
- `chunk_type=algorythm` -> `algorithm`

Page compatibility:

- If only `page` exists, `page_number` is mirrored.
- If only `page_number` exists, `page` is mirrored.

## Fields Not Used by Current Extractors

These are not used by current agent post-processing logic:

- `chapter_title`
- `algorithm_name`
- `title`
- `link_id`

## Change Management

When modifying RAG metadata structure:

1. Update this contract document.
2. Update extractor implementations and tests in `agent-service`.
3. Keep backward compatibility in normalization where feasible.
