---
name: decision-confidence-estimator
description: "Computes a composite confidence score for the current decision by aggregating four signals — sensor reliability, inventory regime stability, inventory uncertainty, and action margin — into a single scalar. Returns a confidence class and a recommended next step (EXECUTE / EXECUTE_WITH_FLAG / DEFER / ESCALATE). Use as the final meta-decision gate before executing any high-stakes action. Questions like 'How confident are we in this decision?', 'Should we execute or wait?', 'Is the data good enough to act on?'"
version: "1.0"
tags: [confidence, meta-decision, Bayesian, posterior, uncertainty, composite]
dependencies: [SKILL-IA-03, SKILL-RE-01, SKILL-RE-03, SKILL-DS-01]
---

# SKILL-MD-01 · Decision Confidence Estimator

## When to Use This Skill

Activate this skill when the user asks about:
- How confident the agent is before executing a recommended action
- Whether the current data quality is sufficient to act
- Whether a decision should be executed, flagged, deferred, or escalated
- As the final gate in any decision pipeline after SKILL-DS-01 has ranked actions
- Questions like *"Are we confident enough to commit this order?"*
  or *"Should we execute now or wait for better sensor data?"*

---

## Core Concept

A Bayesian agent's confidence in a decision is determined by the **sharpness
of its posteriors** across all information sources — not just a single signal.
Wide posteriors signal high uncertainty; narrow posteriors signal high confidence.

This skill draws on two theoretical foundations from *Algorithms for Decision
Making*:

**1. Bayesian posterior width as uncertainty measure (Ch.16 §16.4, eq. 16.6):**
The belief over model parameters is `b(θ) = ∏ Dir(θ^(s,a) | N(s,a))`.
Total count `n = Σ N(s,a)` controls the width of each Dirichlet — larger n
→ narrower posterior → higher confidence. Analogously, each upstream skill
contributes an evidence count that drives its confidence component.

**2. Beta posterior concentration as confidence (Ch.4 §4.2.1, eq. 4.27–4.28):**
For a Beta(α, β) posterior:
- mean = `α / (α + β)`                               (eq. 4.27)
- Posterior is *sharp* (high confidence) when `α + β` is large
- Posterior is *flat* (low confidence) when `α + β` is small (few observations)

The relative standard error (Ch.14 §14.1, eq. 14.6) formalises this:
```
relative_SE = σ̂ / (μ̂ × √n)     (eq. 14.6)
```
High relative SE → low confidence; low relative SE → high confidence.

**Composite confidence score:**
```
C = 0.25 × c_sensor + 0.20 × c_regime + 0.30 × c_uncertainty + 0.25 × c_margin
C = max(0.0, min(1.0, C − penalty))
```

---

## Step-by-Step Execution

### Step 1: Retrieve Bayesian posterior uncertainty from knowledge base

```
search_knowledge_base(
    query="Bayesian posterior uncertainty sharpness concentration total count Dirichlet model confidence",
    k=3
)
```

**What to extract from the result:**
- Ch.16 §16.4, eq. 16.6 — belief over model parameters: `b(θ) = ∏ Dir(θ^(s,a) | N(s,a))`
  Total count `n = sum(alpha)` controls posterior width; used to ground the
  principle that more evidence → narrower posterior → higher decision confidence
- Algorithm 16.8 — `n = sum(model.D[s,a].alpha)` → if n=0, return 0 (no confidence);
  as n grows the posterior concentrates: warehouse analogy — more sensor
  readings and historical moves → higher confidence in inventory estimate

---

### Step 2: Retrieve Beta posterior mean and relative standard error

```
get_entity_by_number(number="4.27")
```

**What to extract from the result:**
- Ch.4 §4.2.1, eq. 4.27 — Beta(α,β) mean = `α / (α+β)`
- Posterior sharpness = `α + β` (total pseudocount); larger → more confident
- Increasing pseudocounts narrows the prior (reduces variance)

```
get_entity_by_number(number="14.6")
```

**What to extract from the result:**
- Ch.14 §14.1, eq. 14.6 — relative standard error: `σ̂ / (μ̂ × √n)`
- This is the operational inverse of confidence: high relative SE → act with
  caution; low relative SE → sufficient precision to execute
- Warehouse mapping: `c_uncertainty = 1 − uncertainty_index` is the
  complement of the relative uncertainty quantified by SKILL-RE-01

---

### Step 3: Get sensor reliability component from SKILL-IA-03

Requires `reliability_score` per device and `low_reliability_device_count`
from `SKILL-IA-03 · Signal Reliability Estimator`.

```
# c_sensor: mean reliability across all active devices ∈ [0,1]
c_sensor = mean(device.reliability_score for device in active_devices)

# penalty for LOW-reliability devices (each degrades overall confidence)
# Grounded in Ch.14 eq.14.6: low-count/noisy sensors inflate relative SE
low_rel_count = count(d for d in devices if d.reliability_class == LOW)
penalty_sensor = 0.15 × low_rel_count
```

If SKILL-IA-03 not run: `c_sensor = 0.5` (neutral), `penalty_sensor = 0`.

---

### Step 4: Get regime stability component from SKILL-RE-03

Requires `regime_label` from `SKILL-RE-03 · Inventory Flow Regime Detector`.

```
# c_regime: stability of the inventory flow regime ∈ [0,1]
# Grounded in Ch.16 §16.4: model uncertainty is higher when the environment
# is in an uncharacterised state (REGIME_SHIFT = unknown transition model)
c_regime = {
    STABLE:               1.0,
    ELEVATED_ADJUSTMENTS: 0.6,
    REGIME_SHIFT:         0.2
}[regime_label]
```

If SKILL-RE-03 not run: `c_regime = 0.8` (assume stable, add warning).

---

### Step 5: Get inventory uncertainty component from SKILL-RE-01

Requires `uncertainty_index` from `SKILL-RE-01 · Inventory Uncertainty Quantifier`.

```
# c_uncertainty: complement of uncertainty index ∈ [0,1]
# Grounded in eq. 14.6: 1 − relative_SE ≈ 1 − uncertainty_index
c_uncertainty = 1.0 - uncertainty_index
```

If SKILL-RE-01 not run: `c_uncertainty = 0.5` (neutral), add warning.

---

### Step 6: Get action margin component from SKILL-DS-01

Requires `margin` and `decision_confidence` from `SKILL-DS-01 · Expected-Utility Action Ranker`.

```
# c_margin: normalised advantage margin ∈ [0,1]
# Grounded in Ch.7 §7.3 eq. 7.15: A(s,a) = Q(s,a) − U(s)
# Large margin → clear winner → high confidence in selection
c_margin = min(margin / 0.10, 1.0)   # saturates at margin ≥ 0.10

# If DS-01 returned TIE, override c_margin to 0
if decision_confidence_ds01 == TIE:
    c_margin = 0.0
```

If SKILL-DS-01 not run: `c_margin = 0.5` (neutral), add warning.

---

### Step 7: Compute composite confidence score

Using the weighted sum grounded in Ch.16 §16.4 (all signals as posterior
concentration contributors, weighted by their relative information value):

```
# Weighted composite — weights sum to 1.0
C_raw = (0.25 × c_sensor
       + 0.20 × c_regime
       + 0.30 × c_uncertainty
       + 0.25 × c_margin)

# Apply sensor penalty (Ch.14 eq.14.6: low-count signals inflate uncertainty)
total_penalty = penalty_sensor   # 0.15 per LOW-reliability device

C = max(0.0, min(1.0, C_raw - total_penalty))
```

---

### Step 8: Classify confidence and recommend next step

```
if C >= 0.75:
    confidence_class      = CONFIDENT
    recommended_next_step = EXECUTE

elif C >= 0.50:
    confidence_class      = ADEQUATE
    recommended_next_step = EXECUTE_WITH_FLAG

elif C >= 0.25:
    confidence_class      = LOW_CONFIDENCE
    recommended_next_step = DEFER

else:
    confidence_class      = INSUFFICIENT
    recommended_next_step = ESCALATE
```

---

### Step 9: Return result

| Field | Value |
|---|---|
| `decision_confidence_score` | Composite C ∈ [0, 1] |
| `confidence_class` | `CONFIDENT` / `ADEQUATE` / `LOW_CONFIDENCE` / `INSUFFICIENT` |
| `recommended_next_step` | `EXECUTE` / `EXECUTE_WITH_FLAG` / `DEFER` / `ESCALATE` |
| `component_scores` | `{c_sensor, c_regime, c_uncertainty, c_margin}` — for audit |
| `weights_used` | `{0.25, 0.20, 0.30, 0.25}` — for audit |
| `penalty_applied` | Total sensor penalty subtracted |
| `low_reliability_device_count` | Number of LOW devices contributing to penalty |

---

## Failure Modes

| Situation | Behaviour |
|---|---|
| All upstream skills missing | All components default to 0.5; `C ≈ 0.50` → ADEQUATE with `data_gap_flag=True` |
| `uncertainty_index = 1.0` (maximum) | `c_uncertainty = 0.0`; strong pull toward LOW_CONFIDENCE or INSUFFICIENT |
| `regime_label = REGIME_SHIFT` | `c_regime = 0.2`; pulls score down even if other signals are strong |
| 2+ LOW-reliability devices | `penalty = 0.30`; can drop ADEQUATE → LOW_CONFIDENCE |
| `decision_confidence_ds01 = TIE` | `c_margin = 0.0`; forces DEFER or ESCALATE unless other signals are very strong |
| `trigger_event = STOCKOUT_IMMINENT` (from DS-03) | Override: `recommended_next_step = EXECUTE` regardless of C; add `stockout_override=True` |

---

## Example Walkthrough

**User query:** *"We've ranked the replenishment options for SKU-6601 — are we confident enough to commit?"*

```
<thinking>
I need to aggregate all four confidence signals into a composite score
and determine whether the decision is ready to execute.
</thinking>

Step 1 — search_knowledge_base("Bayesian posterior uncertainty sharpness concentration total count Dirichlet model confidence")
→ Retrieved: Ch.16 §16.4 eq. 16.6 — b(θ) = ∏ Dir(θ^(s,a) | N(s,a))
  n = sum(alpha) controls posterior width; n=0 → no confidence
→ Principle: confidence grows with total evidence count across all sources

Step 2 — get_entity_by_number(number="4.27")
→ Retrieved: Beta(α,β) mean = α/(α+β)  (eq. 4.27)
  sharpness = α+β; larger pseudocount sum → narrower posterior → more confident

        get_entity_by_number(number="14.6")
→ Retrieved: relative SE = σ̂/(μ̂√n)  (eq. 14.6)
  high relative SE → high uncertainty → lower confidence component

Step 3 — SKILL-IA-03 result:
    device_1: reliability_score=0.82, class=MEDIUM
    device_2: reliability_score=0.91, class=HIGH
    device_3: reliability_score=0.34, class=LOW    ← penalty
    c_sensor      = mean(0.82, 0.91, 0.34) = 0.69
    low_rel_count = 1
    penalty_sensor = 0.15 × 1 = 0.15

Step 4 — SKILL-RE-03 result:
    regime_label = ELEVATED_ADJUSTMENTS
    c_regime     = 0.6

Step 5 — SKILL-RE-01 result:
    uncertainty_index = 0.41  (MODERATE)
    c_uncertainty     = 1 − 0.41 = 0.59

Step 6 — SKILL-DS-01 result:
    margin                = 0.13
    decision_confidence   = HIGH  (margin > 0.10)
    c_margin              = min(0.13 / 0.10, 1.0) = 1.0

Step 7 — Composite:
    C_raw = 0.25×0.69 + 0.20×0.60 + 0.30×0.59 + 0.25×1.0
          = 0.173   + 0.120   + 0.177   + 0.250
          = 0.720
    C     = max(0, min(1, 0.720 − 0.15)) = 0.570

Step 8 — Classify:
    C = 0.570  →  0.50 ≤ C < 0.75  →  ADEQUATE
    recommended_next_step = EXECUTE_WITH_FLAG

Result:
  decision_confidence_score = 0.570
  confidence_class          = ADEQUATE
  recommended_next_step     = EXECUTE_WITH_FLAG
  component_scores          = {c_sensor:0.69, c_regime:0.60,
                                c_uncertainty:0.59, c_margin:1.00}
  penalty_applied           = 0.15  (1 LOW-reliability device)

Confidence is ADEQUATE (0.57). Recommend executing the top-ranked action
but flagging it for review: device_3 is degrading overall confidence
(LOW reliability, −0.15 penalty), and inventory regime shows elevated
adjustments. Consider triggering a cycle count before the next decision
cycle for this SKU.
```

---

## Feeds Into

- `SKILL-MD-02` — receives `confidence_class` and `recommended_next_step`
  to decide whether to defer and how long to wait
- Executor / human reviewer — `recommended_next_step` is the final output
  that determines whether the pipeline commits the action or pauses
- `SKILL-PU-02` — if `DEFER`, re-evaluates VOI to determine whether
  waiting is worth the delay cost