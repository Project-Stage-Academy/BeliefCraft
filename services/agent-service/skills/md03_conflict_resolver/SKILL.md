---
name: signal-conflict-resolver
description: "Detects and resolves conflicts between signals before a decision is committed. Handles three conflict types: Type A (quantity conflict — two sensors report values more than 2σ apart), Type B (action conflict — two ranked pipelines recommend incompatible actions), Type C (model conflict — upstream belief and regime are inconsistent). Returns a resolved quantity or resolved action, the resolution method used, a downgraded confidence delta, and an escalation flag. Use whenever multiple independent signals feed the same decision variable. Questions like 'Sensor A says 140, sensor B says 320 — which do we trust?', 'One pipeline says reorder, another says hold — now what?', 'The signals are contradicting each other.'"
version: "1.0"
tags: [conflict, sensor-fusion, belief-propagation, particle-injection, resolution, meta-decision]
dependencies:
  - bayesian-sensor-belief-updater
  - signal-reliability-estimator
  - expected-utility-action-ranker
  - inventory-flow-regime-detector
---

# Signal Conflict Resolver

## When to Use This Skill

Activate this skill when the user asks about:
- Two or more sensors reporting values that disagree significantly
- Independently run decision pipelines recommending incompatible actions
- Whether to trust a reading that conflicts with the current belief model
- Recovering from a state where the belief has collapsed (particle deprivation analogue)
- Questions like *"Sensor A and sensor B disagree by 180 units — how do we resolve this?"*
  or *"We have two parallel pipelines both recommending different actions for the same SKU."*
  or *"The inventory reading contradicts the regime detector's model — which signal wins?"*

---

## Core Concept

Signal conflicts are the warehouse analogue of two failure modes addressed
in *Algorithms for Decision Making*:

**1. Naive Bayes posterior fusion (Ch.3 §3.3, eq. 3.4–3.8):**
When multiple conditionally independent observations `o₁…oₙ` are available
for the same class variable `C`, the posterior combines them multiplicatively:

```
P(c | o₁:ₙ) ∝ P(c) ∏ᵢ P(oᵢ | c)     (eq. 3.4 + 3.8)
```

Each sensor's reading is one observation. Reliability score `rᵢ` from
`signal-reliability-estimator` plays the role of `P(oᵢ | c)` — higher reliability → higher
weight in the posterior. The resolved quantity is the reliability-weighted
mean across non-outlier sensors, normalised by their total weight.

**2. Particle injection on belief collapse (Ch.19 §19.7, eq. 19.27–19.29):**
When all particles have near-zero weight (particle deprivation), the filter
injects fresh particles from a broader distribution. The injection rate is
driven by the ratio of fast vs slow exponential moving averages:

```
w_fast ← w_fast + α_fast(w_mean − w_fast)     (eq. 19.27)
w_slow ← w_slow + α_slow(w_mean − w_slow)     (eq. 19.28)
m_inject = ⌊m × max(0, 1 − ν × w_fast/w_slow)⌋   (eq. 19.29)
```

Warehouse analogue: when the conflict between observed quantity and prior
belief is so severe that no reconciliation is possible (equivalent to all
particle weights → 0), the agent resets its belief to a broad uninformative
prior — exactly the injection step. This triggers escalation rather than
proceeding with a collapsed belief.

**Three conflict types and their resolution strategies:**

| Type | Trigger | Resolution method |
|---|---|---|
| A — Quantity | `|μ_A − μ_B| > 2 × σ_pooled` | Reliability-weighted mean (eq. 3.4–3.8 analogue) |
| B — Action | Two pipelines recommend incompatible actions | Priority hierarchy: STOCKOUT_IMMINENT > REORDER > MONITOR |
| C — Model | Resolved quantity diverges from regime model by > 3σ | Belief reset (particle injection analogue, eq. 19.27–19.29); escalate |

---

## Step-by-Step Execution

### Step 1: Retrieve belief propagation and Naive Bayes fusion from knowledge base

```
search_knowledge_base(
    query="Naive Bayes posterior multiple observations conditional independence reliability weighted product normalise",
    k=3
)
```

**What to extract from the result:**
- Ch.3 §3.3, eq. 3.4 — `P(c, o₁:ₙ) = P(c) ∏ᵢ P(oᵢ | c)` — joint distribution
  under conditional independence of observations given class
- Ch.3 §3.3, eq. 3.8 — `P(c | o₁:ₙ) ∝ P(c) ∏ᵢ P(oᵢ | c)` — posterior
  is proportional to prior × product of likelihoods
- Warehouse mapping: each sensor reading `μᵢ` is an observation; reliability
  score `rᵢ` is the likelihood weight; resolved quantity = weighted mean.

```
search_knowledge_base(
    query="particle injection deprivation belief collapse adaptive injection weight fast slow exponential moving average reset",
    k=3
)
```

**What to extract from the result:**
- Ch.19 §19.7, eq. 19.27–19.29 — adaptive injection tracks fast and slow
  exponential moving averages of mean particle weight; when `w_fast << w_slow`
  the filter injects particles from a broader distribution
- The algorithm (19.2) note: if all observation weights → 0, return uniform
  distribution — this is the belief collapse / escalation trigger
- Warehouse mapping: a Type C conflict (resolved quantity inconsistent with
  regime model) is equivalent to particle deprivation — the belief must be
  reset and the decision escalated for human review

---

### Step 2: Retrieve Naive Bayes posterior equation and particle injection formula

```
get_entity_by_number(number="3.8")
```

**What to extract from the result:**
- `P(c | o₁:ₙ) ∝ P(c) ∏ᵢ P(oᵢ | c)` (eq. 3.8)
- The proportionality constant κ normalises so that `Σ_c P(c | o₁:ₙ) = 1`
- Warehouse formula derived from this:
  `μ_resolved = Σᵢ (rᵢ × μᵢ) / Σᵢ rᵢ`   (reliability weights as likelihoods)

```
get_entity_by_number(number="19.29")
```

**What to extract from the result:**
- `m_inject = ⌊m × max(0, 1 − ν × w_fast/w_slow)⌋` (eq. 19.29)
- Injections increase as `w_fast/w_slow` drops below `1/ν` — the belief
  is losing contact with reality
- Warehouse mapping: if `|μ_resolved − μ_regime| > 3σ_regime`, inject a
  broad uninformative belief (reset posterior) and set `escalation_required=True`

---

### Step 3: Detect conflict type

Collect all competing signal values. Sources:
- `bayesian-sensor-belief-updater` outputs: one `posterior_mean` + `posterior_std` per sensor/pipeline
- `signal-reliability-estimator` outputs: `reliability_score` per device
- `expected-utility-action-ranker` outputs: `top_action_id` + `trigger_event` per pipeline
- `inventory-flow-regime-detector` outputs: `baseline_mean`, `baseline_std` (regime model)

#### Type A — Quantity conflict

```
# Pooled uncertainty across all sensor posteriors
σ_pooled = sqrt(mean(σᵢ² for all sensors i))

# Flag conflict if any pair diverges by > 2σ_pooled
type_A_detected = any(
    |μᵢ − μⱼ| > 2 × σ_pooled
    for all pairs (i, j)
)

# Identify outlier: sensor whose reading is furthest from the median
median_qty = median(μᵢ for all i)
outlier_sensor = argmax_i |μᵢ − median_qty|
```

#### Type B — Action conflict

```
# Conflict if two pipelines recommend actions with incompatible types
incompatible_pairs = {
    (EMERGENCY_ORDER, MONITOR),
    (EMERGENCY_ORDER, HOLD),
    (PLACE_ORDER,     HOLD),
}

type_B_detected = any(
    (action_i, action_j) in incompatible_pairs
    for all pairs (i, j) of pipeline recommendations
)
```

#### Type C — Model conflict

```
# After Type A resolution, check resolved quantity against regime model
# (requires inventory-flow-regime-detector baseline_mean and baseline_std)
μ_regime  = baseline_mean   # from inventory-flow-regime-detector
σ_regime  = baseline_std

type_C_detected = (
    type_A_detected AND
    |μ_resolved − μ_regime| > 3 × σ_regime
)
```

---

### Step 4: Resolve each detected conflict

#### Resolve Type A — Reliability-weighted mean (eq. 3.8 analogue)

```
# Exclude outlier_sensor if its reliability < 0.4 (unreliable reading)
active_sensors = [i for i in sensors
                  if i != outlier_sensor OR reliability_score[i] >= 0.4]

# Reliability-weighted mean (Naive Bayes posterior fusion)
# rᵢ plays the role of P(oᵢ | c) — likelihood of the observation
μ_resolved = sum(reliability_score[i] × μᵢ for i in active_sensors)
           / sum(reliability_score[i] for i in active_sensors)

σ_resolved = sqrt(
    sum(reliability_score[i] × (μᵢ − μ_resolved)²
        for i in active_sensors)
    / sum(reliability_score[i] for i in active_sensors)
)

resolution_method_A = RELIABILITY_WEIGHTED_MEAN
```

If only one sensor remains after outlier exclusion:
```
μ_resolved = μ_remaining
σ_resolved = σ_remaining
resolution_method_A = SINGLE_SOURCE_FALLBACK
```

#### Resolve Type B — Priority hierarchy

Apply a strict priority order grounded in STOCKOUT_IMMINENT bypass rule
from `decision-deferral-controller` (critical states always override normal states):

```
PRIORITY = {
    STOCKOUT_IMMINENT: 4,   # absolute override
    REORDER_TRIGGER:   3,
    PIPELINE_RISK:     2,
    NORMAL:            1,
}

resolved_action = pipeline with highest PRIORITY[trigger_event]

# Tiebreak: higher action_utility_score from expected-utility-action-ranker
if tie: resolved_action = pipeline with higher action_utility_score

resolution_method_B = PRIORITY_HIERARCHY
```

#### Resolve Type C — Belief reset (particle injection analogue, eq. 19.29)

```
# Type C: resolved quantity has drifted > 3σ from regime model
# Analogue: w_fast/w_slow << 1/ν → inject from broad distribution
# Action: reset to uninformative prior; escalate

μ_resolved        = μ_regime          # fall back to regime baseline
σ_resolved        = σ_regime × 2.0    # doubled width = broad injection
escalation_required = True
resolution_method_C = BELIEF_RESET_ESCALATE
```

---

### Step 5: Compute confidence downgrade

Each detected conflict type reduces decision confidence by a fixed delta,
applied additively to the `decision_confidence_score` from `decision-confidence-estimator`:

```
confidence_delta = 0.0

if type_A_detected:
    conflict_severity_A = |μ_outlier − μ_resolved| / σ_resolved
    # Mild (2–3σ): −0.10 | Moderate (3–5σ): −0.20 | Severe (>5σ): −0.35
    confidence_delta -= {
        conflict_severity_A <= 3: 0.10,
        conflict_severity_A <= 5: 0.20,
        True:                     0.35
    }

if type_B_detected:
    confidence_delta -= 0.15   # action conflict always reduces confidence

if type_C_detected:
    confidence_delta -= 0.40   # model conflict is severe; forces ESCALATE
```

---

### Step 6: Return result

| Field | Value |
|---|---|
| `conflict_detected` | `True` / `False` |
| `conflict_types` | List of detected types: `[A]`, `[B]`, `[A, C]`, etc. |
| `resolved_quantity` | `μ_resolved` — best estimate after Type A resolution |
| `resolved_quantity_std` | `σ_resolved` |
| `resolved_action` | `top_action_id` after Type B resolution |
| `resolution_method` | Per type: `RELIABILITY_WEIGHTED_MEAN` / `SINGLE_SOURCE_FALLBACK` / `PRIORITY_HIERARCHY` / `BELIEF_RESET_ESCALATE` |
| `outlier_sensor_id` | Device ID of the outlier sensor (Type A only) |
| `confidence_delta` | Negative adjustment to apply to `decision-confidence-estimator` score |
| `escalation_required` | `True` if Type C detected (belief reset triggered) |

---

## Failure Modes

| Situation | Behaviour |
|---|---|
| Only one sensor available | `type_A_detected=False`; no conflict possible; pass through as-is |
| All sensors have `reliability_score < 0.2` | No reliable source to weight; `resolution_method=SINGLE_SOURCE_FALLBACK` using highest-reliability sensor; add warning |
| `inventory-flow-regime-detector` not run (no regime baseline) | Skip Type C check; `type_C_detected=False`; add `regime_check_skipped=True` |
| `expected-utility-action-ranker` not run (no action scores) | Type B tiebreak falls back to trigger_event priority only |
| Type A and Type B both detected | Resolve independently; combine `confidence_delta`; use resolved_quantity for Type B re-evaluation if needed |
| All sensor weights sum to zero | Treat as belief collapse; set `escalation_required=True`, return `resolution_method=BELIEF_RESET_ESCALATE` |

---

## Example Walkthrough

**User query:** *"Sensor A reads 140 units, sensor B reads 320 units for SKU-2204 — the signals are contradicting each other. Which do we trust?"*

```
<thinking>
Two sensors are far apart. I need to detect the conflict type, apply
the Naive Bayes reliability-weighted fusion, check against the regime
model, compute the confidence downgrade, and return a resolved quantity.
</thinking>

Step 1 — search_knowledge_base("Naive Bayes posterior multiple observations conditional independence reliability weighted product normalise")
→ Retrieved: Ch.3 §3.3 eq. 3.4 — P(c,o₁:ₙ) = P(c) ∏ᵢ P(oᵢ|c)
  Conditional independence of observations given class variable
→ Retrieved: Ch.3 §3.3 eq. 3.8 — P(c|o₁:ₙ) ∝ P(c) ∏ᵢ P(oᵢ|c)
  Posterior proportional to product of likelihoods (normalised by κ)
  Warehouse mapping: rᵢ ≈ P(oᵢ|c); μ_resolved = Σ(rᵢ μᵢ)/Σrᵢ

        search_knowledge_base("particle injection deprivation belief collapse adaptive injection weight fast slow exponential moving average reset")
→ Retrieved: Ch.19 §19.7 eq. 19.29 — m_inject = ⌊m × max(0, 1−ν×w_fast/w_slow)⌋
  When w_fast << w_slow the belief has collapsed; inject from broad distribution
→ Algorithm 19.2: "if sum(b') ≈ 0 return uniform" — zero-weight observation
  triggers uninformative fallback (belief reset)

Step 2 — get_entity_by_number(number="3.8")
→ P(c|o₁:ₙ) ∝ P(c) ∏ᵢ P(oᵢ|c)  (eq. 3.8)
  κ normalises to sum-to-1
  Derived formula: μ_resolved = Σᵢ(rᵢ × μᵢ) / Σᵢ rᵢ

        get_entity_by_number(number="19.29")
→ m_inject = ⌊m × max(0, 1−ν×w_fast/w_slow)⌋  (eq. 19.29)
  |μ_resolved − μ_regime| > 3σ_regime → inject broad belief → escalate

Step 3 — Detect conflicts:
    Sensor A: μ_A = 140, σ_A = 18.0, reliability = 0.88  (HIGH)
    Sensor B: μ_B = 320, σ_B = 25.0, reliability = 0.41  (LOW)

    σ_pooled = sqrt(mean(18² , 25²)) = sqrt(mean(324, 625)) = sqrt(474.5) = 21.8

    Type A: |140 − 320| = 180 > 2 × 21.8 = 43.6  ✓  DETECTED
    median_qty = 230  → outlier = Sensor B  (|320−230|=90 > |140−230|=90, tie → pick B lower reliability)
    type_B: not applicable (single SKU, no parallel pipelines)

Step 4 — Resolve Type A:
    Sensor B reliability = 0.41 ≥ 0.4  → include (borderline)

    μ_resolved = (0.88×140 + 0.41×320) / (0.88 + 0.41)
               = (123.2 + 131.2) / 1.29
               = 254.4 / 1.29
               = 197.2 units

    σ_resolved = sqrt(
        (0.88×(140−197.2)² + 0.41×(320−197.2)²) / 1.29
    ) = sqrt((0.88×3271.8 + 0.41×15075.8) / 1.29)
      = sqrt((2879.2 + 6181.1) / 1.29)
      = sqrt(7023.5) = 83.8 units

    Check Type C vs regime:
    μ_regime = 210, σ_regime = 35  (from `inventory-flow-regime-detector`)
    |197.2 − 210| = 12.8 < 3 × 35 = 105  → Type C NOT detected

Step 5 — Confidence downgrade:
    conflict_severity_A = |320 − 197.2| / 83.8 = 122.8 / 83.8 = 1.47σ
    Wait — use |μ_outlier − μ_resolved| / σ_resolved = 122.8 / 83.8 = 1.47
    But the raw gap was 180 / σ_pooled = 180 / 21.8 = 8.3σ  → SEVERE (> 5σ)
    confidence_delta = −0.35

Step 6 — Result:
    conflict_detected     = True
    conflict_types        = [A]
    resolved_quantity     = 197.2 units
    resolved_quantity_std = 83.8 units
    resolution_method     = RELIABILITY_WEIGHTED_MEAN
    outlier_sensor_id     = sensor_B
    confidence_delta      = −0.35
    escalation_required   = False

Sensor A (reliability=0.88, HIGH) receives 68% of the weight;
Sensor B (reliability=0.41, LOW) receives 32%. Resolved estimate:
197 units ±84. The severe gap (8.3σ) triggers a −0.35 confidence
penalty — subtract this from the MD-01 score before executing.
Schedule a physical cycle count to determine ground truth.
```

---

## Feeds Into

- `decision-confidence-estimator` — apply `confidence_delta` to `decision_confidence_score`
  before classifying confidence class; may push ADEQUATE → LOW_CONFIDENCE
- `bayesian-sensor-belief-updater` — `resolved_quantity` replaces the conflicted posterior mean
  as the canonical inventory estimate for all downstream calculations
- `decision-deferral-controller` — `escalation_required=True` (Type C) is equivalent to
  `INSUFFICIENT` confidence; deferral controller must trigger ESCALATE
- `expected-utility-action-ranker` — after Type B resolution, re-run ranking with only the
  `resolved_action`'s pipeline to confirm the utility scores are consistent
