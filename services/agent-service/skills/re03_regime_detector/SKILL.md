---
name: inventory-flow-regime-detector
description: "Detects whether inventory adjustment patterns have shifted from historical baseline — distinguishing normal operations from elevated shrinkage, counting errors, or a structural regime change. Use when inventory discrepancies seem unusual, before trusting adjustment data for replenishment decisions, or when auditing a warehouse. Questions like 'Is the shrinkage rate normal this week?', 'Have inventory adjustments increased recently?', 'Is something wrong with the counting process in Warehouse C?'"
version: "1.0"
tags: [inventory, regime, anomaly, adjustments, shrinkage, model-update]
dependencies: []
---

# SKILL-RE-03 · Inventory Flow Regime Detector

## When to Use This Skill

Activate this skill when the user asks about:
- Whether recent inventory adjustments are within normal range
- Whether shrinkage or counting errors have increased unexpectedly
- Whether a warehouse is experiencing a structural change in flow patterns
- As a prerequisite before using adjustment data in replenishment decisions
- Questions like *"Is Warehouse C showing abnormal inventory losses this week?"*
  or *"Has something changed in how inventory is being counted?"*

---

## Core Concept

Normal inventory operations produce adjustments within a stable statistical
baseline. When the recent adjustment rate exceeds the historical mean by more
than 2 standard deviations, a **regime shift** may have occurred.

This skill applies two complementary ideas from *Algorithms for Decision Making*:

1. **Incremental mean estimation** (Ch.17 §17.1, eq. 17.1–17.5):
   Track the running mean of the adjustment ratio as new data arrives.
   `x̂ₘ = x̂ₘ₋₁ + α(m) × (x⁽ᵐ⁾ − x̂ₘ₋₁)`

2. **Bayesian model estimation** (Ch.15 §15.2):
   Treat each time window as a Bernoulli trial (anomalous / normal) and
   maintain a Beta posterior over the true anomaly rate — the same mechanism
   used for bandit arm estimation.

A regime is flagged when the 7-day adjustment ratio exceeds the 90-day
rolling mean by more than 2σ, consistent with the robustness / stress-testing
framework of Ch.14 §14.3.

---

## Step-by-Step Execution

### Step 1: Retrieve incremental mean estimation formula from knowledge base

```
search_knowledge_base(
    query="incremental estimation mean learning rate update rule sample running average",
    k=3
)
```

**What to extract from the result:**
- Incremental update rule (Ch.17 §17.1, eq. 17.4–17.5):
  `x̂ₘ = x̂ₘ₋₁ + α(m) × (x⁽ᵐ⁾ − x̂ₘ₋₁)`
- Sample mean formula (eq. 17.1): `x̂ₘ = (1/m) Σ x⁽ⁱ⁾`
- Use these to compute rolling mean and std of the adjustment ratio
  over a 90-day baseline window

---

### Step 2: Retrieve exact equation for Bayesian bandit model update

```
get_entity_by_number(number="15.1")
```

**What to extract from the result:**
- Bayesian posterior win-probability formula (Ch.15 §15.2, eq. 15.1):
  `ρₐ = (wₐ + 1) / (wₐ + ℓₐ + 2)`
- Use this to track the posterior probability that the current window
  is anomalous: `w` = anomalous days, `ℓ` = normal days in the window
- This gives a calibrated anomaly probability alongside the threshold test

---

### Step 3: Retrieve robustness / stress-test threshold framing

```
search_knowledge_base(
    query="robustness analysis stress test deviation model perturbation threshold evaluation",
    k=2
)
```

**What to extract from the result:**
- Ch.14 §14.3 — evaluate system under model deviations:
  flag REGIME_SHIFT when observed behaviour falls outside the plausible
  range of the baseline model (mean ± 2σ is the standard stress boundary)

---

### Step 4: Fetch 7-day and 30-day adjustment summaries

```
GET /api/v1/smart-query/inventory/adjustments-summary
    ?product_id=<product_id>
    &window_days=7

GET /api/v1/smart-query/inventory/adjustments-summary
    ?product_id=<product_id>
    &window_days=30
```

**Fields to extract:** `total_adjustments`, `total_units_adjusted`,
`dominant_reason_code`, `adjustment_count`

Compute:
```
adjustment_ratio_7d  = total_adjustments_7d  / total_moves_7d
adjustment_ratio_30d = total_adjustments_30d / total_moves_30d
```

---

### Step 5: Fetch 90-day baseline from inventory moves

```
GET /api/v1/smart-query/inventory/moves
    ?product_id=<product_id>
    &start_date=<now - 90 days>
    &end_date=<now - 31 days>
```

**Fields to extract per move:** `move_type`, `reported_qty`, `actual_qty`,
`reason_code`, `occurred_at`

Using the incremental mean from Step 1:
```
# Compute baseline adjustment ratio (rolling 90-day excluding last 30)
baseline_mean = mean(daily_adjustment_ratios over 90d window)
baseline_std  = std(daily_adjustment_ratios over 90d window)

# Compute discrepancy rate (reported vs actual quantities)
discrepancy_rate = mean(|reported_qty - actual_qty| / max(qty, 1))
```

---

### Step 6: Compute Bayesian anomaly posterior

Using eq. 15.1 from Step 2:

```
# Count anomalous days in last 7d (days where ratio > baseline_mean + 2σ)
w = anomalous_days_count
ℓ = normal_days_count   (= 7 − w)

# Bayesian posterior anomaly probability (Beta-Binomial, eq. 15.1)
p_anomalous = (w + 1) / (w + ℓ + 2)
```

---

### Step 7: Classify regime

Using the 2σ stress-test boundary from Step 3:

```
shift_threshold = baseline_mean + 2 × baseline_std

if adjustment_ratio_7d > shift_threshold AND p_anomalous > 0.7:
    regime_label   = REGIME_SHIFT
    shift_detected_at = first day ratio exceeded threshold

elif adjustment_ratio_7d > baseline_mean + baseline_std:
    regime_label = ELEVATED_ADJUSTMENTS

else:
    regime_label = STABLE
```

---

### Step 8: Return result

| Field | Value |
|---|---|
| `regime_label` | `STABLE` / `ELEVATED_ADJUSTMENTS` / `REGIME_SHIFT` |
| `adjustment_ratio_7d` | Recent 7-day adjustment ratio |
| `adjustment_ratio_30d` | 30-day adjustment ratio |
| `baseline_mean` | 90-day rolling mean of adjustment ratio |
| `baseline_std` | 90-day rolling std |
| `discrepancy_rate` | Mean reported vs actual qty mismatch |
| `dominant_reason_code` | Most frequent adjustment reason in the window |
| `p_anomalous` | Bayesian posterior probability of anomalous regime |
| `shift_detected_at` | Timestamp when ratio first exceeded 2σ threshold |

---

## Failure Modes

| Situation | Behaviour |
|---|---|
| Fewer than 14 days of move history | Return `regime_label=STABLE`, `data_gap_flag=True`, warn insufficient history |
| No baseline data (new product) | Return `regime_label=STABLE` with warning, `p_anomalous=0.5` (uniform prior) |
| `adjustments-summary` endpoint unavailable | `data_gap_flag=True`, skip regime classification |
| All moves have `reported_qty = actual_qty` | `discrepancy_rate=0.0`, likely perfect data or no scanning — add warning |

---

## Example Walkthrough

**User query:** *"Is Warehouse C showing abnormal inventory losses for SKU-3301 this week?"*

```
<thinking>
I need to compare the recent adjustment rate against the historical
baseline using incremental mean estimation and Bayesian anomaly scoring.
</thinking>

Step 1 — search_knowledge_base("incremental estimation mean learning rate update rule running average")
→ Retrieved eq. 17.1–17.5: x̂ₘ = (1/m) Σ x⁽ⁱ⁾,  update: x̂ₘ = x̂ₘ₋₁ + α(x⁽ᵐ⁾ − x̂ₘ₋₁)

Step 2 — get_entity_by_number(number="15.1")
→ Retrieved: ρₐ = (wₐ + 1) / (wₐ + ℓₐ + 2)  [Bayesian bandit posterior, Ch.15 §15.2]

Step 3 — search_knowledge_base("robustness stress test deviation threshold evaluation")
→ Confirmed: flag regime shift when observation exceeds baseline ± 2σ (Ch.14 §14.3)

Step 4 — GET /adjustments-summary?product_id=SKU-3301&window_days=7
→ adjustment_ratio_7d = 0.18, dominant_reason_code = "shrinkage"

        GET /adjustments-summary?product_id=SKU-3301&window_days=30
→ adjustment_ratio_30d = 0.11

Step 5 — GET /inventory/moves (90-day baseline, days -90 to -31)
→ baseline_mean = 0.07,  baseline_std = 0.02
→ discrepancy_rate = 0.09  (reported vs actual mismatch)

Step 6 — Bayesian anomaly posterior:
    Anomalous days in last 7d: w=5  (ratio > 0.07 + 2×0.02 = 0.11)
    Normal days: ℓ=2
    p_anomalous = (5+1)/(5+2+2) = 6/9 = 0.67 → below 0.7 threshold

Step 7 — Classify:
    shift_threshold = 0.07 + 2×0.02 = 0.11
    adjustment_ratio_7d = 0.18 > 0.11  ✓
    p_anomalous = 0.67 < 0.70          ✗ (just below)
    → regime_label = ELEVATED_ADJUSTMENTS

Result:
  regime_label      = ELEVATED_ADJUSTMENTS
  adjustment_ratio_7d = 0.18  (baseline: 0.07 ± 0.02)
  p_anomalous       = 0.67
  dominant_reason   = shrinkage
  discrepancy_rate  = 0.09

Warehouse C shows elevated adjustments for SKU-3301 — 2.6× the baseline rate,
mostly coded as shrinkage. Not yet a confirmed regime shift (Bayesian confidence
67%), but warrants a cycle count and security review within 48 hours.
```

---

## Feeds Into

- `SKILL-MD-03` — uses `regime_label` to weight signal conflict resolution
- `SKILL-MD-01` — applies confidence penalty when `regime_label = REGIME_SHIFT`
- `SKILL-PU-02` — elevated regime triggers VOI recalculation (gather more info first)
- `SKILL-DS-03` — `REGIME_SHIFT` overrides threshold trigger to conservative mode
