---
name: inventory-uncertainty-quantifier
description: "Converts a posterior belief distribution over inventory quantity into a single interpretable uncertainty index, combining statistical spread (coefficient of variation), information-theoretic entropy, data staleness, and quality status. Use before any high-stakes decision to understand how much to trust the inventory estimate. Questions like 'How confident are we in this stock level?', 'Is this inventory estimate reliable enough to commit?', 'How stale is this data?'"
version: "1.0"
tags: [inventory, uncertainty, entropy, belief, POMDP, risk]
dependencies:
  - bayesian-sensor-belief-updater
---

# Inventory Uncertainty Quantifier

## When to Use This Skill

Activate this skill when the user asks about:
- How reliable or trustworthy the current inventory estimate is
- Whether the stock level estimate is precise enough to base a decision on
- How stale the last physical count is and whether it affects confidence
- As a prerequisite before `multi-attribute-utility-scorer`, `expected-utility-action-ranker`, `decision-confidence-estimator`
- Questions like *"Can we trust this stock estimate for the allocation decision?"*
  or *"How uncertain is our inventory position for SKU-X in Warehouse Y?"*

---

## Core Concept

A posterior belief `b(s) = N(μ, σ²)` from `bayesian-sensor-belief-updater` quantifies what we know
about the true inventory quantity. But the raw `σ` alone is not decision-ready —
it needs to be combined with data staleness and quality status into a single
normalised **uncertainty index** ∈ [0, 1].

This skill applies two complementary measures from *Algorithms for Decision Making*:

1. **Coefficient of Variation (CV)** — relative spread of the posterior (Ch.2 §2.2):
   `CV = σ / max(μ, 1)` — scale-free measure of dispersion

2. **Differential Entropy of the Gaussian posterior** (Appendix A.8–A.9):
   `h(X) = ½ × ln(2πe × σ²)` — information-theoretic uncertainty of the belief state

Both are then penalised for staleness and quality to produce `uncertainty_index`.

---

## Step-by-Step Execution

### Step 1: Retrieve entropy and uncertainty measures from knowledge base

```
search_knowledge_base(
    query="entropy uncertainty measure belief distribution Gaussian differential entropy variance information content",
    k=3
)
```

**What to extract from the result:**
- Entropy definition (Appendix A.8, eq. A.8–A.9):
  `H(X) = −∑ P(x) log P(x)` for discrete;
  `h(X) = −∫ p(x) log p(x) dx` for continuous (differential entropy)
- For a Gaussian: `h(X) = ½ × ln(2πe × σ²)`
- Coefficient of variation as relative spread: `CV = σ / μ`
- POMDP belief state as sufficient statistic (Ch.19 §19.1):
  the belief `b` summarises all relevant past information — its spread
  directly measures decision uncertainty

---

### Step 2: Expand linked staleness and quality penalty concepts

```
expand_graph_by_ids(
    ids=[<ids from step 1>]
)
```

**What to extract from the result:**
- Diffuse initial belief guidance (Ch.19 §19.1): the older the last physical
  count, the less informative the prior — uncertainty should grow with staleness
- Observation quality as evidence reliability: degraded quality status reduces
  effective confidence in the posterior

---

### Step 3: Retrieve `bayesian-sensor-belief-updater` outputs (upstream dependency)

This skill requires the posterior from `bayesian-sensor-belief-updater` as input.
If `data_gap_flag=True` is set on the upstream result, return safe default immediately.

**Required fields from `bayesian-sensor-belief-updater`:**
`posterior_mean (μ)`, `posterior_std (σ)`, `effective_confidence`, `data_quality_label`

---

### Step 4: Fetch inventory balance metadata

```
GET /api/v1/smart-query/inventory/observed-snapshot
    ?product_id=<product_id>
    &location_id=<location_id>
```

Extract `last_count_at` and `quality_status` from `inventory_balances`.

Compute staleness:
```
staleness_days = (now − last_count_at).days
```

---

### Step 5: Compute uncertainty index

Using the formulas from Step 1:

```
# 1. Coefficient of Variation (Ch.2 §2.2)
CV = σ / max(μ, 1)

# 2. Differential entropy of Gaussian posterior (Appendix A.9)
#    h(X) = ½ × ln(2πe × σ²)  — normalise to [0,1] by capping at σ=50
import math
h_raw = 0.5 * math.log(2 * math.pi * math.e * max(σ, 0.01) ** 2)
h_norm = min(max(h_raw / 0.5 * math.log(2 * math.pi * math.e * 50**2), 0), 1)

# 3. Staleness penalty (Ch.19 §19.1 — belief degrades without fresh observations)
staleness_penalty = min(staleness_days × 0.02, 0.5)

# 4. Quality penalty
quality_penalty = 0.2  if quality_status not in ('good', 'verified')
                  0.0  otherwise

# 5. Combined uncertainty index
uncertainty_index = min(
    0.5 × CV + 0.3 × h_norm + staleness_penalty + quality_penalty,
    1.0
)

# 6. Classify
uncertainty_class = CERTAIN      if uncertainty_index <  0.10
                    LOW           if uncertainty_index <  0.30
                    MODERATE      if uncertainty_index <  0.60
                    HIGH          if uncertainty_index >= 0.60
```

---

### Step 6: Return result

| Field | Value |
|---|---|
| `uncertainty_index` | Normalised uncertainty [0–1] |
| `uncertainty_class` | `CERTAIN` / `LOW` / `MODERATE` / `HIGH` |
| `cv` | Coefficient of variation (σ / μ) |
| `entropy_approx` | Differential entropy of the posterior |
| `staleness_days` | Days since last physical count |
| `staleness_penalty` | Penalty applied for data age |
| `quality_penalty` | Penalty applied for non-good quality status |

---

## Failure Modes

| Situation | Behaviour |
|---|---|
| `bayesian-sensor-belief-updater` `data_gap_flag=True` | Return `uncertainty_class=HIGH`, `uncertainty_index=1.0`, `data_gap_flag=True` |
| `last_count_at` missing | Assume `staleness_days=30` (conservative) |
| `posterior_mean=0` and `posterior_std=0` | `CV=0`, `uncertainty_class=CERTAIN` — flag as suspicious |
| `quality_status=quarantine` or `damaged` | `quality_penalty=0.2`, add warning |

---

## Example Walkthrough

**User query:** *"Is our inventory position for SKU-7712 in Warehouse A reliable enough to commit 500 units to this order?"*

```
<thinking>
I need to quantify how uncertain we are about the true inventory level
before committing stock. I'll run `inventory-uncertainty-quantifier` on top of `bayesian-sensor-belief-updater` output.
</thinking>

Step 1 — search_knowledge_base("entropy uncertainty measure belief distribution Gaussian differential entropy variance")
→ Retrieved: h(X) = ½ ln(2πe σ²) from Appendix A.9, CV = σ/μ from Ch.2 §2.2

Step 2 — expand_graph_by_ids([doc_id_1, doc_id_2])
→ Confirmed: belief degrades without fresh observations (Ch.19 §19.1)
→ staleness penalty grows linearly at 0.02/day

Step 3 — `bayesian-sensor-belief-updater` result:
    posterior_mean = 541.2,  posterior_std = 38.4
    effective_confidence = 0.73,  data_quality_label = "good"

Step 4 — GET /observed-snapshot → last_count_at = "2026-02-20"
    staleness_days = 20

Step 5 — Compute:
    CV              = 38.4 / 541.2 = 0.071
    h_raw           = ½ × ln(2π × e × 38.4²) = 4.87
    h_norm          = 4.87 / 6.12 = 0.796
    staleness_penalty = min(20 × 0.02, 0.5) = 0.40
    quality_penalty   = 0.0   (status = "good")
    uncertainty_index = min(0.5 × 0.071 + 0.3 × 0.796 + 0.40, 1.0)
                      = min(0.035 + 0.239 + 0.40, 1.0) = 0.674

    uncertainty_class = HIGH  (≥ 0.60)

Result:
  uncertainty_index = 0.674  →  HIGH
  Main driver: data is 20 days stale (last physical count: Feb 20)

The inventory estimate (541 units) may be sufficient for 500 committed,
but HIGH uncertainty driven by stale data means we cannot be confident.
Recommend: trigger a cycle count before committing, or apply safety buffer.
```

---

## Feeds Into

- `value-of-information` — uses `uncertainty_index` to compute Value of Information (VOI)
- `expected-utility-action-ranker` — uses `uncertainty_index` to compute confidence intervals around action scores
- `decision-confidence-estimator` — uses `uncertainty_class` as `c_uncertainty` factor in decision confidence
- `threshold-based-trigger-decision` — uses `uncertainty_index` to decide whether to defer or act immediately
