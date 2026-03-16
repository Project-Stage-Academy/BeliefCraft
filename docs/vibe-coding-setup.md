# Vibe Coding Configuration

This document describes the unified configuration management for "vibe coding" tools (Cursor, Gemini CLI, Claude Code, VS Code, Codex) used in the BeliefCraft project.

## Overview

The project uses a single source of truth for Model Context Protocol (MCP) server configurations and AI agent instructions to ensure consistency across all AI-assisted development environments.

### Source of Truth for MCP
- **`.mcp.json`**: The central configuration file at the root of the repository. This file is also natively used by **Claude Code**.

### Synchronized Targets
When `.mcp.json` is modified, the following files are automatically updated:
- **`.cursor/mcp.json`**: Cursor specific configuration.
- **`.gemini/settings.json`**: Gemini CLI specific configuration.
- **`.vscode/mcp.json`**: VS Code specific configuration.
- **`.codex/config.toml`**: Codex specific configuration (TOML format).

### Current MCP Servers
The project currently utilizes the following MCP servers:
- **`weaviate-docs`**: Provides semantic retrieval over Weaviate's documentation and knowledge sources.
- **`context7`**: Provides context retrieval for many different documentation sources (AWS, Boto3, Langgraph, etc.).

## AI Agent Context Files

Instructions for AI agents are distributed through Markdown files to provide localized and hierarchical context:

- **`AGENTS.md`**: Instructions for all AI agents.
- **`GEMINI.md`**: Instructions for the Gemini CLI agent. Links to `AGENTS.md`.
- **`CLAUDE.md`**: Instructions for the Claude Code agent. Links to `AGENTS.md`.

These files are present at the project root and within specific directories to provide "surgical" context depending on where the agent is operating.

## AI Agent Skills

To ensure high instruction adherence and clean context, the development workflow is split into granular, specialized "skills". Each skill corresponds to a specific phase of the Test-Driven Development (TDD) lifecycle.

### Source of Truth for Skills
- **`.agents/skills/`**: Used by most agents. Contains the source definition for each skill (e.g., `plan`, `test`, `implement`, `refactor`, `document`, `context-engineering`).

### Synchronized Skill Targets
Skills are synchronized from the source directory to tool-specific locations to ensure all agents use the same instructions:
- **`.claude/skills/`**: For Claude Code.
- **`.github/skills/`**: For GitHub Copilot.
- **`.agent/skills/`**: For Antigravity.

### Skill Activation
Agents should activate the relevant skill before starting work in a phase:
- **Gemini CLI**: Uses `activate_skill(name)`.
- **Other Agents**: Read the `SKILL.md` file within the corresponding skill directory (e.g., `.agents/skills/plan/SKILL.md`).

### Skill Synchronization Hook
A pre-commit hook automatically runs `scripts/sync_skills.py` to keep all skill directories in sync.

#### Manual Synchronization
Run:
```bash
uv run python scripts/sync_skills.py
```

## Adding New MCP Servers

To add a new MCP server:
1. Edit `.mcp.json` at the project root.
2. Add your server configuration under `mcpServers`.
3. Commit your changes. The pre-commit hook will update all tool-specific files.

Example `.mcp.json`:
```json
{
  "mcpServers": {
    "my-new-server": {
      "url": "http://localhost:8000/mcp",
      "type": "http"
    }
  }
}
```

## Synchronization Hook

A pre-commit hook automatically runs `scripts/sync_mcp_config.py` to keep all configurations in sync.

### Manual Synchronization
You can manually trigger the synchronization by running:
```bash
uv run python scripts/sync_mcp_config.py
```

## IDE Specific Notes

### Antigravity & PyCharm
Currently, **Antigravity** and **PyCharm** do not support project-specific MCP configuration files. For these tools, you must manually add the MCP servers to your **global** configuration if you wish to use them.

## Verification
Tests for the synchronization logic are located in `tests/hooks/test_vibe_code_synchronizer.py`.
