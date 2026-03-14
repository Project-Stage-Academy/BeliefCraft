# Skills Directory

This directory contains **domain expertise packages** for the warehouse ReAct agent.

## What is a Skill?

A skill is a self-contained decision workflow that allows the agent to solve complex warehouse operations problems by combining API calls, MCP tool calls against a knowledge base, and formulas from *Algorithms for Decision Making* (Kochenderfer et al., MIT Press 2022).

Each skill is a directory containing:

- **SKILL.md** (mandatory) — YAML frontmatter + step-by-step agent instructions
- Supporting files (optional) — additional `.md` files referenced from SKILL.md

## Architecture

The skills system uses a **three-tier information retrieval** strategy to keep the agent's context lean:

### Tier 1: Discovery
- Agent sees only skill names and descriptions at startup
- Lightweight catalog injected into the system prompt
- Generated from YAML frontmatter `name` and `description` fields

### Tier 2: Activation
- Agent calls `load_skill(skill_name)` to retrieve the full SKILL.md body
- Returns primary instructions and a list of any supporting files
- Cached in Redis (24-hour TTL)

### Tier 3: Deep Dive
- Agent calls `read_skill_file(skill_name, filename)` for supporting context
- Used only when SKILL.md explicitly references additional files

## Skill Execution Contract

Every skill is backed by a `BaseSkill` subclass (`base/skill_result.py`).

```python
class BaseSkill:
    async def run(self, inputs: dict[str, Any]) -> SkillResult: ...
    def _safe_default(self, reason: str) -> SkillResult: ...
```

- `run()` must never raise an unhandled exception
- `run()` must always return a `SkillResult`
- `_safe_default()` must return a conservative result with `data_gap_flag=True`
- All inputs arrive through the `inputs` dict — no direct DB or API calls in `__init__`

```python
@dataclass
class SkillResult:
    skill_id:      str
    outputs:       dict[str, Any]
    data_gap_flag: bool       = False   # True when result is a safe default
    confidence:    float      = 1.0
    warnings:      list[str]  = field(default_factory=list)
```

## MCP Tools Available Inside Skills

Each SKILL.md instructs the agent to call these MCP tools before applying any formulas:

| Tool | Purpose |
|---|---|
| `search_knowledge_base(query, k)` | Semantic search over the Kochenderfer et al. book |
| `expand_graph_by_ids(ids)` | Retrieve linked concepts for given document IDs |
| `get_entity_by_number(number)` | Precise retrieval by equation or figure number |

**Every skill begins with a `search_knowledge_base` call** — the agent retrieves the relevant theory at runtime rather than relying on training knowledge.

## Available Skills

### Category IA — Information Assessment

| Directory | Skill name | Key dependencies |
|---|---|---|
| `ia01_sensor_belief_updater/` | `bayesian-sensor-belief-updater` | — |
| `ia02_supplier_reliability_aggregator/` | `supplier-reliability-aggregator` | — |
| `ia03_signal_reliability_estimator/` | `signal-reliability-estimator` | — |

### Category RE — Risk Evaluation

| Directory | Skill name | Key dependencies |
|---|---|---|
| `re01_uncertainty_quantifier/` | `inventory-uncertainty-quantifier` | SKILL-IA-01 |
| `re02_leadtime_risk_estimator/` | `leadtime-risk-estimator` | SKILL-IA-02 |
| `re03_regime_detector/` | `inventory-flow-regime-detector` | — |

### Category PU — Preference & Utility

| Directory | Skill name | Key dependencies |
|---|---|---|
| `pu01_utility_scorer/` | `multi-attribute-utility-scorer` | SKILL-IA-02, SKILL-RE-02 |
| `pu02_value_of_information/` | `value-of-information` | SKILL-PU-01, SKILL-RE-01 |
| `pu03_constraint_validator/` | `constraint-satisfaction-validator` | — |

### Category DS — Decision Selection

| Directory | Skill name | Key dependencies |
|---|---|---|
| `ds01_action_ranker/` | `expected-utility-action-ranker` | SKILL-PU-01, SKILL-PU-03, SKILL-RE-01 |
| `ds02_dominance_filter/` | `stochastic-dominance-filter` | SKILL-PU-01 |
| `ds03_threshold_trigger/` | `threshold-based-trigger-decision` | SKILL-IA-01 |

### Category MD — Meta-Decision

| Directory | Skill name | Key dependencies |
|---|---|---|
| `md01_confidence_estimator/` | `decision-confidence-estimator` | SKILL-IA-03, SKILL-RE-01, SKILL-RE-03, SKILL-DS-01 |
| `md02_deferral_controller/` | `decision-deferral-controller` | SKILL-PU-02, SKILL-MD-01, SKILL-RE-01, SKILL-DS-03 |
| `md03_conflict_resolver/` | `signal-conflict-resolver` | SKILL-IA-01, SKILL-IA-03, SKILL-DS-01, SKILL-RE-03 |

## Typical Decision Pipeline

Skills are designed to be composed in sequence. A full replenishment decision follows this order:

```
IA-01  Calibrate sensor readings          (posterior quantity estimate)
IA-02  Aggregate supplier reliability     (Beta posterior per supplier)
IA-03  Estimate signal reliability        (per-device trust score)
   ↓
RE-01  Quantify inventory uncertainty     (uncertainty index)
RE-02  Estimate lead-time risk            (P95/P99 lead time)
RE-03  Detect inventory flow regime       (STABLE / REGIME_SHIFT / …)
   ↓
PU-01  Score candidate actions            (multi-attribute utility)
PU-02  Evaluate value of information      (VOI — act now or gather more?)
PU-03  Validate constraints               (capacity, quality, allocation)
   ↓
DS-02  Filter dominated actions           (Pareto frontier)
DS-03  Classify trigger event             (STOCKOUT_IMMINENT / REORDER / …)
DS-01  Rank actions by expected utility   (beam-width = 3)
   ↓
MD-03  Resolve signal conflicts           (if multiple sensors disagree)
MD-01  Estimate decision confidence       (composite score → EXECUTE / DEFER / …)
MD-02  Control deferral                   (explore-then-commit, max 2 deferrals)
```

Not all skills are required on every call. DS-03 is typically the entry-point classifier; MD-03 is invoked only when a conflict is detected.

## Skill Authoring Guidelines

### YAML Frontmatter (required)

```yaml
---
name: skill-name-kebab-case
description: "Shown in the agent's Tier 1 catalog. Write it as a trigger sentence: what question does this skill answer?"
version: "1.0"
tags: [category, domain, keywords]
dependencies: [SKILL-XX-NN]   # upstream skills whose outputs this skill consumes
---
```

### Markdown Body Structure

1. **Skill Title** — `# SKILL-XX-NN · Human-Readable Name`
2. **When to Use** — explicit trigger phrases and user questions
3. **Core Concept** — theory grounding with chapter, section, and equation references
4. **Step-by-Step Execution** — numbered steps, each with the exact MCP tool call, fields to extract, and formula in a code block
5. **Failure Modes** — table of degraded-data scenarios and fallback behaviour
6. **Example Walkthrough** — concrete numbers, full step-by-step trace inside a `<thinking>` block
7. **Feeds Into** — which downstream skills consume which output fields

### Rules

- Every skill **must** start with `search_knowledge_base` — the agent retrieves theory at runtime
- Every skill **must** have at least one `get_entity_by_number` call for the key equation
- Formulas go in code blocks, not prose
- `Fields to extract:` must list specific field names after every API call
- `Feeds Into` must name the exact output field and how it is used downstream

### Security

- Supporting file paths must be relative — no `..` or absolute paths
- All skill content is validated on load
- SkillStore prevents directory traversal attacks

## Technical Implementation

| Component | Location |
|---|---|
| Base interface | `base/skill_result.py` |
| SkillStore (scanner + loader) | `app/services/skill_store/` |
| Skill tools (`load_skill`, `read_skill_file`) | `app/tools/skill_tools.py` |
| Redis cache | 24-hour TTL, keyed by skill name |
| System prompt injection | `WAREHOUSE_ADVISOR_SYSTEM_PROMPT` |
