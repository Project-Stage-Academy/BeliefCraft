---
name: context-engineering
description: Self-correction and instruction-update logic. Use when a mistake is corrected by the user, a validation fails, or a friction point is identified. Never repeat a mistake.
---

# Context Engineering Skill

This skill is the brain of the self-correction loop. It ensures that every lesson learned from a mistake or correction is permanently encoded into the instruction set.

## Workflow

1.  **Analyze Mistake**: Identify the root cause (e.g., outdated instruction, ambiguous naming, missing edge case).
2.  **Categorization**: Determine where the fix belongs:
    - **Global `AGENTS.md`**: Architectural or universal rules.
    - **Local `AGENTS.md`**: Service-specific domain rules (e.g., `agent-service`).
    - **Workflow Skill**: Task-specific rules (e.g., `test` skill).
3.  **Atomic Update**: Surgically update the `Common Mistakes to Avoid` section in the target file using the standardized format:
    - **Context**: When does the mistake happen?
    - **Mistake**: What specifically went wrong?
    - **Correction**: What is the correct behavior?
4.  **Sync**: Trigger the skill synchronization script(repo_root_folder/scripts/sync_skills.py) to ensure all platforms are updated.

## Mandates

- **Standardized Format**: Use clear, concise language in the "Common Mistakes" section.
- **Permanent Correction**: Every time a user corrects you, this skill MUST be activated to update instructions.
- **Surgical Precision**: Do not rewrite the entire file; use targeted updates for the specific mistake.
- **No Redundancy**: If a mistake is already documented, refine the existing rule for better clarity instead of adding a new one.
- **Be Concise**: Keep each mistake and correction pair to one or two sentences! Context is not infinite!

## Common Mistakes Strategy

- **Architectural or always need to know**: Place in root `AGENTS.md` (e.g., "Always use `uv run`").
- **Task/skill specific**: Place in relevant skill (e.g., "No `# Arrange` comments" goes in `test` skill).
- **Service Domain**: Place in `services/*/AGENTS.md` (e.g., "RAG tools are discovered via MCP").

## Canonical Example

```markdown
### Common Mistakes to Avoid (Format)
- **[Context] [Mistake]**: [Correction]
- **TDD Step 2**: Labeling sections with `# Arrange/Act/Assert`: Use only blank lines to separate sections for better readability.
```
