---
name: bayesian-sensor-belief-updater
description: "Calibrates noisy sensor readings into a trustworthy posterior distribution over true inventory quantity. Use when a raw observed_qty cannot be trusted at face value — e.g. before replenishment decisions, allocation commits, or when sensor health is degraded. Questions like 'How much do we actually have?', 'Can I trust this reading?', 'What is the real stock level given sensor noise?'"
version: "1.0"
tags: [inventory, belief-update, sensor, uncertainty, bayesian]
dependencies: []
---

# SKILL-IA-01 · Bayesian Sensor Belief Updater

## When to Use This Skill

Activate this skill when the user asks about:
- True inventory level at a specific location when sensor reliability is in question
- Whether a sensor reading is trustworthy before making a high-stakes decision
- Calibrated stock estimates that account for device noise, bias, or missing readings
- Questions like *"How much of SKU-X do we really have in Warehouse Y?"*

---

## Core Concept

Raw sensor observations are noisy. This skill applies the **Kalman filter belief update** (Ch.19 §19.3, *Algorithms for Decision Making*) to combine:
- A **prior** (last known inventory level)
- A **likelihood** (sensor reading, adjusted for device noise and bias)

...into a **posterior** — the best estimate of true quantity given all available evidence.

---

## Step-by-Step Execution

### Step 1: Retrieve the Kalman filter update formula from the knowledge base

```
search_knowledge_base(
    query="Kalman filter belief update posterior mean covariance predict step update step",
    k=3
)
```

**What to extract from the result:**
- Predict step (eq. 19.12–19.13): `μ_p`, `Σ_p`
- Update step (eq. 19.14–19.16): Kalman gain `K`, posterior `μ_b'`, `Σ_b'`
- The scalar simplification for 1-D state: `K = σ²_prior / (σ²_prior + σ²_sensor)`

---

### Step 2: Expand linked concepts for missing-observation handling

Take the document IDs returned in Step 1 and call:

```
expand_graph_by_ids(
    ids=[<ids from step 1>]
)
```

**What to extract from the result:**
- Belief initialization rule (Ch.19 §19.1): when observation is missing,
  the posterior collapses to the prior — do not update, only inflate uncertainty

---

### Step 3: Fetch the latest sensor observation

```
GET /api/v1/smart-query/inventory/observed-snapshot
    ?product_id=<product_id>
    &location_id=<location_id>
```

**Fields to extract:** `observed_qty`, `confidence`, `is_missing`,
`device_id`, `quality_status`, `reported_noise_sigma`

**Decision point:**
- If `observed_qty` is null → go directly to Step 6 (safe default)
- If `quality_status` is `quarantine` or `damaged` → add 0.2 to uncertainty after update

---

### Step 4: Fetch device parameters

```
GET /api/v1/smart-query/devices/{device_id}
```

**Fields to extract:** `noise_sigma`, `bias`, `missing_rate`, `status`

**Known patterns:**
- `status = offline` → treat as missing observation
- `bias ≠ 0` → must correct observation before update: `o_corrected = observed_qty − bias`
- `noise_sigma = 0` → perfect sensor, observation is ground truth

---

### Step 5: Apply the Kalman update

Using the formula retrieved in Step 1, apply the scalar form:

```
o_corrected = observed_qty − bias

If is_missing = True:                        # Ch.19 §19.1 — uninformative update
    posterior_mean       = prior_mean
    posterior_std        = prior_std × 1.5   # inflate uncertainty
    effective_confidence = confidence × 0.3

Else:
    K              = σ²_prior / (σ²_prior + σ²_sensor)    # Kalman gain
    posterior_mean = prior_mean + K × (o_corrected − prior_mean)
    posterior_std  = sqrt((1 − K) × σ²_prior)
    effective_confidence = confidence

posterior_mean = max(0.0, posterior_mean)    # inventory cannot be negative
```

**Note:** if `reported_noise_sigma` is present in the observation, use it instead of device `noise_sigma`.

---

### Step 6: Return result

| Field | Value |
|---|---|
| `posterior_mean` | Best estimate of true on-hand quantity |
| `posterior_std` | Uncertainty around the estimate |
| `effective_confidence` | Reliability score [0–1] |
| `data_quality_label` | `quality_status` from inventory_balances |
| `update_timestamp` | Current UTC timestamp |
| `device_id` | Sensor used |
| `bias_applied` | Bias correction applied |
| `is_missing` | Whether the observation was missing |

---

## Failure Modes

| Situation | Behaviour |
|---|---|
| Observation endpoint unavailable | Return safe default: `posterior_std=50.0`, `data_gap_flag=True` |
| Device record not found | Return safe default with warning |
| `is_missing=True` | Uninformative update — posterior = prior, confidence × 0.3 |
| `noise_sigma=0` | Observation is ground truth, `posterior_std=0.0` |
| Negative posterior mean | Clip to `0.0` |

---

## Example Walkthrough

**User query:** *"Can we commit 200 units of SKU-4821 from Warehouse B to this order?"*

```
<thinking>
Before committing stock, I need to verify the true inventory level — 
the raw sensor reading may not be reliable. I'll run SKILL-IA-01.
</thinking>

Step 1 — search_knowledge_base("Kalman filter belief update posterior mean...")
→ Retrieved eq. 19.14–19.16: K = σ²_prior/(σ²_prior + σ²_sensor), posterior mean/std formulas

Step 2 — expand_graph_by_ids([doc_id_1, doc_id_2])
→ Confirmed: missing observation rule from §19.1

Step 3 — GET /observed-snapshot?product_id=SKU-4821&location_id=WH-B-12
→ observed_qty=214, confidence=0.61, is_missing=False, device_id=D-449

Step 4 — GET /devices/D-449
→ noise_sigma=18.0, bias=3.0, status=active

Step 5 — Apply Kalman update:
    o_corrected = 214 − 3.0 = 211
    K           = 2500 / (2500 + 324) = 0.885
    posterior_mean = 200 + 0.885 × (211 − 200) = 209.7
    posterior_std  = sqrt((1 − 0.885) × 2500) = 16.9

Result:
  posterior_mean = 209.7 units
  posterior_std  = 16.9 units
  effective_confidence = 0.61

Committing 200 units is feasible — the posterior mean is 209.7 with std 16.9,
meaning P(true_qty ≥ 200) ≈ 72%. Recommend confirming with a physical count
before committing given moderate confidence (0.61).
```

---

## Feeds Into

- `SKILL-RE-01` — uses `posterior_mean`, `posterior_std` to compute uncertainty index
- `SKILL-MD-01` — uses `effective_confidence` in overall decision confidence
- `SKILL-MD-03` — compares posteriors across devices to resolve conflicts