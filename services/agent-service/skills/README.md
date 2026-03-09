# Skills Directory

This directory contains **domain expertise packages** for the ReAct agent.

## What is a Skill?

A skill is a self-contained diagnostic workflow that allows the agent to solve complex warehouse operations problems using expert knowledge. Each skill is stored as a directory containing:

- **SKILL.md** (mandatory) - YAML frontmatter + markdown instructions
- Supporting files (optional) - additional `.md` files for deep-dive context

## Progressive Disclosure Architecture

The skills system implements a **three-tier information retrieval** strategy to prevent context poisoning and excessive token usage:

### Tier 1: Discovery
- Agent sees only skill names and descriptions at startup
- Lightweight catalog injected into system prompt
- Generated from YAML frontmatter metadata

### Tier 2: Activation
- Agent calls `load_skill(skill_name)` to retrieve full SKILL.md body
- Returns primary instructions and list of supporting files
- Cached in Redis (24-hour TTL)

### Tier 3: Deep Dive
- Agent calls `read_skill_file(skill_name, filename)` for specific context
- Retrieves supporting documentation (checklists, algorithms, data schemas)
- Used only when SKILL.md references additional details

## Available Skills

Skills are organized by operational domain:

- **inventory-discrepancy-audit/** - Diagnostic workflow for inventory shrinkage and discrepancy analysis
- **procurement-risk-assessment/** - Supplier reliability and lead time risk evaluation
- **capacity-pressure-analysis/** - Warehouse space utilization and bottleneck detection
- **sensor-reliability-check/** - IoT device health monitoring and data quality assessment
- **demand-observation-snapshot/** - Real-time demand pattern analysis

## Skill Authoring Guidelines

### YAML Frontmatter (Required)

```yaml
---
name: skill-name-kebab-case
description: Brief summary shown in agent's catalog (triggers Claude's attention)
version: "1.0"
tags: [category, domain, keywords]
dependencies: []  # Optional: other skills required
---
```

### Markdown Body Structure

1. **Skill Title** - High-level name of expertise
2. **When to Use** - Specific triggers and scenarios
3. **Instructions** - Step-by-step guidance with tool calls
4. **Examples** - Sample inputs and analytical reasoning

### Security Notes

- Supporting file paths must be relative (no `..` or absolute paths)
- All skill content is validated on load
- SkillStore prevents directory traversal attacks

## Technical Implementation

- **SkillStore** - Metadata scanner and content loader (`app/services/skill_store/`)
- **Skill Tools** - `load_skill()` and `read_skill_file()` integrated with tool registry
- **Caching** - Redis-backed with 24-hour TTL for static knowledge
- **Integration** - Catalog automatically injected into `WAREHOUSE_ADVISOR_SYSTEM_PROMPT`
