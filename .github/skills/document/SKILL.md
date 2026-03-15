---
name: document
description: Step 5 of TDD. Finalize documentation in `/docs`, docstrings, and context files. Update context-engineering records if needed. Use after refactoring is complete.
---

# Document Skill (TDD Step 5)

This skill focuses on ensuring that all changes are reflected in the project's documentation and that all context files (e.g., AGENTS.md) are up to date.

## Workflow

1.  **Codebase Reflection**: Ensure all public functions and classes have updated Google-style docstrings explaining the "why" and "how."
2.  **API Contract (`docs/api/`)**: Update the relevant service file (e.g., `agent-service.md`) if endpoints, request/response models, or tool registries changed.
3.  **Architectural Contract (`docs/architecture/`)**:
    - Update `overview.md` if the system map or data flow between services was modified.
    - Create a new ADR in `adrs/` using `template.md` for significant structural decisions.
4.  **Service Deep Dive (`docs/rag-service/` etc.)**: Update service-specific logic documents (e.g., `vector-db-workflow.md`, `CONFIGURATION.md`) for internal technical changes.
5.  **Operational Contract (`docs/runbooks/`, `docs/deployment/`)**: Update setup, deployment, or debugging guides if environment variables or dependencies changed.
6.  **Context Maintenance**: Review and update the root or service-specific `AGENTS.md` if directories, commands, or patterns changed.
7.  **Context Engineering**: If a mistake was corrected during this feature lifecycle, activate the `context-engineering` skill.

## Mandates

- **Unified Consistency**: Ensure naming, formatting, and validation rules (e.g., Pydantic constraints) in documentation match the code exactly.
- **Registered Tool Set**: If adding an agent tool, it MUST be listed in the "Registered Tool Set" section of the relevant API doc.
- **Traceability**: If a new service or package was added, update the "Repository Structure" in all relevant context files.
- **No Documentation Drift**: Verify that the final code implementation aligns with the updated documentation before finishing.

## Common Mistakes

- **Skipping Step 5**: Never finish a task without documenting it.
- **Stale ADRs**: Ensure the status of ADRs is correctly updated (Proposed -> Accepted).
- **Vague Request/Response**: Always include exact JSON shapes and validation rules in API docs.

## Canonical Example

```markdown
### POST `/api/v1/agent/analyze`
Runs ReAct reasoning for a user query.

**Request body (`AgentQueryRequest`)**:
- `query` (str): Min 10, Max 1000 chars.
- `max_iterations` (int): Range 1..20.

**Response body (`AgentQueryResponse`)**:
- `status`: "completed" | "failed"
- `answer`: The final reasoning result.
```
