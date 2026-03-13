---
name: value-of-information
description: "Computes whether it is worth gathering more information (e.g. triggering a cycle count) before acting, or whether the agent should act now on current beliefs. Uses the VOI framework to compare expected utility with vs without additional observation, net of the cost of counting. Use before high-stakes decisions under HIGH uncertainty. Questions like 'Should we count stock before committing this order?', 'Is it worth waiting for more data?', 'Does gathering more information change our decision?'"
version: "1.0"
tags: [VOI, value-of-information, decision, uncertainty, count, defer]
dependencies: [SKILL-PU-01, SKILL-RE-01]
---

# SKILL-PU-02 · Trade-Off Evaluator (Value of Information)

## When to Use This Skill

Activate this skill when the user asks about:
- Whether to act now or gather more data first (cycle count, re-scan, wait for PO)
- Whether the cost of a physical count is justified by the decision at stake
- Whether inventory uncertainty is high enough to change the optimal action
- Questions like *"Should we do a cycle count before committing this large order?"*
  or *"Is waiting for a fresh sensor reading worth the delay?"*

---

## Core Concept

The **Value of Information** (Ch.6 §6.6, *Algorithms for Decision Making*, eq. 6.9)
measures how much expected utility increases if we observe an additional variable O'
before deciding:

```
VOI(O' | o) = [Σ_{o'} P(o' | o) × EU*(o, o')] − EU*(o)     (eq. 6.9)
```

Where:
- `EU*(o)` = best expected utility achievable with current information
- `EU*(o, o')` = best expected utility if we additionally observe `o'`
- `P(o' | o)` = predictive distribution over the new observation

VOI is **never negative** — observing more data can only help or be neutral.
But observation has a cost. The net VOI determines whether to act or gather info:

```
VOI_net = VOI_gross − cost_of_observation
ACT_NOW      if VOI_net ≤ 0
GATHER_INFO  if VOI_net > 0
```

---

## Step-by-Step Execution

### Step 1: Retrieve VOI formula from knowledge base

```
search_knowledge_base(
    query="value of information expected utility observation variable VOI increase utility cost",
    k=3
)
```

**What to extract from the result:**
- VOI definition (Ch.6 §6.6, eq. 6.9):
  `VOI(O'|o) = [Σ_{o'} P(o'|o) × EU*(o,o')] − EU*(o)`
- VOI is non-negative: if new observation changes no decision, VOI = 0
- Net VOI: subtract cost of observation — only gather info if net VOI > 0

---

### Step 2: Retrieve exact VOI equation

```
get_entity_by_number(number="6.9")
```

**What to extract from the result:**
- Exact formula and interpretation: VOI = expected gain in optimal EU
  from observing O', averaged over its predictive distribution P(o'|o)
- Key insight: if `EU*(o, o') = EU*(o)` for all o' → VOI = 0 → act now

---

### Step 3: Get current best EU from SKILL-PU-01

Requires `action_utility_score` (best scoring action) from `SKILL-PU-01`.
This is `EU*(o)` — the utility of the best action given current information.

If `SKILL-PU-01` was not run, use `uncertainty_index` from `SKILL-RE-01`
as a proxy: high uncertainty → assume current EU is suboptimal.

---

### Step 4: Get uncertainty index from SKILL-RE-01

Requires `uncertainty_index` and `posterior_mean (μ)`, `posterior_std (σ)`
from `SKILL-RE-01` / `SKILL-IA-01`.

These parameterise `P(o' | o)` — the predictive distribution over what
a cycle count would reveal:

```
# Simulate two representative future observations (high / low qty scenario)
qty_high = μ + 2σ     # optimistic scenario
qty_low  = max(0, μ − 2σ)   # pessimistic scenario
P(qty_high | o) = 0.5
P(qty_low  | o) = 0.5
```

---

### Step 5: Simulate EU under each future observation

For each simulated observation `o'` ∈ {qty_high, qty_low}:

Re-score the best action using the updated fill rate and penalty exposure
(same formula as `SKILL-PU-01 Step 4`) with `qty_allocated = min(qty_ordered, o')`:

```
EU*(o, qty_high) = utility score if true qty = μ + 2σ
EU*(o, qty_low)  = utility score if true qty = μ − 2σ
```

---

### Step 6: Compute VOI gross and net

Using eq. 6.9 from Step 2:

```
# VOI gross (eq. 6.9)
VOI_gross = [0.5 × EU*(o, qty_high) + 0.5 × EU*(o, qty_low)] − EU*(o)

# Cost of observation (cycle count default = 0.05 utility units, configurable)
cost_of_count = 0.05

# Net VOI
VOI_net = VOI_gross − cost_of_count

# Recommendation
if VOI_net > 0:
    recommendation = GATHER_INFO
else:
    recommendation = ACT_NOW

# Breakeven uncertainty threshold
# VOI = 0 when σ is small enough that qty_high ≈ qty_low ≈ μ
# Approximate: breakeven_σ such that VOI_gross = cost_of_count
breakeven_uncertainty = cost_of_count / (∂EU/∂σ)   # linear approximation
```

---

### Step 7: Fetch pipeline context (optional enrichment)

```
GET /api/v1/smart-query/procurement/pipeline-summary
    ?supplier_id=<supplier_id>
    &status_in=open,pending
```

**Fields to extract:** `next_expected_at_min`

Use this to estimate whether GATHER_INFO is feasible within the decision window:
if next shipment arrives within 2 days, waiting may be free (no count needed).

---

### Step 8: Return result

| Field | Value |
|---|---|
| `voi_gross` | Raw VOI before cost (eq. 6.9) |
| `voi_net` | VOI after subtracting cost of observation |
| `recommendation` | `ACT_NOW` / `GATHER_INFO` |
| `breakeven_uncertainty_threshold` | σ below which acting now is optimal |
| `cost_of_count_assumed` | Cost parameter used (default 0.05) |
| `eu_current` | `EU*(o)` — best utility with current info |
| `eu_with_info` | `Σ P(o') EU*(o,o')` — expected utility after observing |

---

## Failure Modes

| Situation | Behaviour |
|---|---|
| `SKILL-PU-01` not run | Use `uncertainty_index` as proxy; `voi_gross` is approximate |
| `uncertainty_index = 0` (CERTAIN) | `VOI_gross = 0`, `recommendation = ACT_NOW` immediately |
| `posterior_std = 0` | No scenario spread possible, `VOI_gross = 0`, act now |
| Pipeline endpoint unavailable | Skip enrichment, proceed with count recommendation only |

---

## Example Walkthrough

**User query:** *"Before we commit 400 units of SKU-2201 to this priority order, should we do a cycle count first?"*

```
<thinking>
This is a VOI decision — is the expected utility gain from a cycle count
worth more than the cost of doing it? I'll compute VOI_net.
</thinking>

Step 1 — search_knowledge_base("value of information expected utility observation variable VOI cost")
→ Retrieved: VOI(O'|o) = [Σ P(o'|o) EU*(o,o')] − EU*(o)  (eq. 6.9)
→ Confirmed: VOI ≥ 0, subtract observation cost to get net VOI

Step 2 — get_entity_by_number(number="6.9")
→ Confirmed: VOI = 0 if new observation changes no optimal action

Step 3 — SKILL-PU-01 result:
    EU*(o) = 0.71  (best action: commit 400 units, fill_rate=0.89)

Step 4 — SKILL-RE-01 result:
    posterior_mean = 448.0,  posterior_std = 61.0
    uncertainty_index = 0.64  (HIGH)

    qty_high = 448 + 122 = 570   → P=0.5
    qty_low  = max(0, 448 − 122) = 326  → P=0.5

Step 5 — Re-score under each scenario:
    EU*(o, qty_high=570): fill_rate=400/400=1.0 → U=0.88
    EU*(o, qty_low=326):  fill_rate=326/400=0.815 → U=0.54

Step 6 — Compute VOI:
    VOI_gross = 0.5×0.88 + 0.5×0.54 − 0.71
              = 0.71 − 0.71 = 0.00

    Wait — qty_low scenario gives U=0.54 < current EU=0.71
    This means current action is risky: if true qty=326, we over-commit.

    VOI_gross = 0.5×0.88 + 0.5×0.54 − 0.71 = 0.71 − 0.71 = 0.00
    VOI_net   = 0.00 − 0.05 = −0.05

    recommendation = ACT_NOW  (VOI_net < 0)

Step 7 — GET /pipeline-summary: next shipment in 1 day → count not feasible anyway

Result:
  voi_net        = −0.05
  recommendation = ACT_NOW
  eu_current     = 0.71

VOI is near zero — the cycle count cost (0.05) exceeds the expected gain.
However, the pessimistic scenario (326 units) would cause a 74-unit shortfall.
Recommend: commit 326 units conservatively (the pessimistic quantity),
not 400, to avoid penalty exposure under HIGH uncertainty.
```

---

## Feeds Into

- `SKILL-MD-02` — uses `recommendation` and `voi_net` to decide whether to defer
- `SKILL-DS-01` — if `GATHER_INFO`, pauses action ranking until new data arrives
- `SKILL-MD-01` — uses `voi_net` as signal of decision readiness