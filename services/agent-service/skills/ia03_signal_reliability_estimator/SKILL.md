---
name: signal-reliability-estimator
description: "Classifies the reliability of each sensor device contributing to inventory observations by combining device health metrics into a single reliability score. Use before trusting any sensor reading, before running `bayesian-sensor-belief-updater`, or when diagnosing why inventory data looks suspicious. Questions like 'Can I trust the sensors in Warehouse B?', 'Which devices are degraded right now?', 'Why does the inventory data look noisy today?'"
version: "1.0"
tags: [sensor, reliability, device-health, anomaly, naive-bayes]
dependencies: []
---

# Signal Reliability Estimator

## When to Use This Skill

Activate this skill when the user asks about:
- Whether sensor data from a specific warehouse or location can be trusted
- Which devices are currently degraded or anomalous
- Why inventory readings look inconsistent or noisy
- As a prerequisite check before running `bayesian-sensor-belief-updater` or `signal-conflict-resolver`
- Questions like *"Are our sensors in Warehouse B reliable right now?"*
  or *"Which devices should I not trust today?"*

---

## Core Concept

Each device contributes to inventory observations with some level of trustworthiness.
This skill uses a **Naive Bayes classification** approach (Ch.3 §3.3,
*Algorithms for Decision Making*) to classify each device as HIGH / MEDIUM / LOW
reliability by combining independent evidence signals:

```
P(reliable | features) ∝ P(reliable) × ∏ P(feature_i | reliable)   (eq. 3.4)
```

The three independent evidence features are:
1. **Average confidence** from recent observations (`avg_confidence`)
2. **Excess missing rate** — how much above the configured `missing_rate` the device is actually missing
3. **Anomaly flag** — whether the device is flagged in the anomaly report

These features are treated as conditionally independent given the reliability class
(the defining assumption of Naive Bayes), allowing a simple multiplicative scoring rule.

---

## Step-by-Step Execution

### Step 1: Retrieve Naive Bayes classification framework from knowledge base

```
search_knowledge_base(
    query="Naive Bayes classification conditional independence posterior probability features class",
    k=3
)
```

**What to extract from the result:**
- Joint probability factorization (Ch.3 §3.3, eq. 3.4):
  `P(c, o₁:ₙ) = P(c) × ∏ P(oᵢ | c)`
- Posterior classification rule (eq. 3.5–3.8):
  `P(c | o₁:ₙ) ∝ P(c) × ∏ P(oᵢ | c)`
- Conditional independence assumption: features are independent given the class

---

### Step 2: Expand linked belief initialization concepts

```
expand_graph_by_ids(
    ids=[<ids from step 1>]
)
```

**What to extract from the result:**
- How to initialize belief under uncertainty (Ch.19 §19.1):
  use a diffuse prior when device history is limited — avoid overconfidence
  in the reliability class without sufficient observation history

---

### Step 3: Fetch device health summary (7-day window)

```
GET /api/v1/smart-query/devices/health-summary
```

**Fields to extract per device:**
`device_id`, `avg_confidence`, `observed_missing_rate`, `configured_missing_rate`,
`status`, `warehouse_id`, `device_type`

---

### Step 4: Fetch device anomaly report

```
GET /api/v1/smart-query/devices/anomalies
```

**Fields to extract per device:**
`device_id`, `anomaly_count`, `last_anomaly_at`, `anomaly_type`

**Known patterns:**
- `anomaly_count > 5` in 24 hours → hardware or placement issue
- `anomaly_type = calibration_drift` → systematic bias, affects all readings
- `anomaly_type = signal_loss` → intermittent, inflates missing rate

---

### Step 5: Fetch individual device parameters (for each flagged device)

```
GET /api/v1/smart-query/devices/{device_id}
```

**Fields to extract:** `noise_sigma`, `bias`, `missing_rate`, `status`

---

### Step 6: Compute reliability score per device

Using the Naive Bayes factorization from Step 1, compute a reliability score
by multiplying three independent evidence factors:

```
# Feature 1: confidence factor
f_confidence = avg_confidence                     # ∈ [0, 1]

# Feature 2: excess missing rate factor
excess_missing = max(0, observed_missing_rate − configured_missing_rate)
f_missing = 1 − excess_missing                   # penalise excess missingness

# Feature 3: anomaly penalty factor
f_anomaly = 0.6  if device flagged in anomaly report
            1.0  otherwise

# Combined reliability score (Naive Bayes product of factors)
reliability_score = f_confidence × f_missing × f_anomaly

# Classify
reliability_class = HIGH    if reliability_score >= 0.8
                    MEDIUM  if reliability_score >= 0.5
                    LOW     if reliability_score <  0.5
```

**Decision point:**
- `status = offline` → immediately assign `reliability_class = LOW`,
  `reliability_score = 0.0`, skip other factors
- `bias ≠ 0` → add warning that bias correction is required before trusting readings

---

### Step 7: Return result per device

| Field | Value |
|---|---|
| `device_id` | Device identifier |
| `reliability_score` | Composite score [0–1] |
| `reliability_class` | `HIGH` / `MEDIUM` / `LOW` |
| `anomaly_detected` | Boolean |
| `excess_missing_rate` | Observed − configured missing rate |
| `avg_confidence` | Average confidence from 7-day health summary |
| `requires_bias_correction` | Boolean — `True` if `bias ≠ 0` |
| `warnings` | List of specific issues found |

**Summary fields (across all devices):**
| Field | Value |
|---|---|
| `low_reliability_device_count` | Number of LOW devices |
| `data_trustworthy` | `True` if no LOW-reliability devices in scope |

---

## Failure Modes

| Situation | Behaviour |
|---|---|
| Health summary endpoint unavailable | Return `data_gap_flag=True`, warn all devices untrusted |
| Anomaly endpoint unavailable | Skip anomaly factor (`f_anomaly=1.0`), add warning |
| Device record not found | Use health-summary values only, log warning |
| All devices `LOW` | Set `data_trustworthy=False`, recommend physical count |
| No observation history (new device) | Use diffuse prior per Ch.19 §19.1 — `reliability_class=MEDIUM`, warn |

---

## Example Walkthrough

**User query:** *"Can I trust the inventory data coming from Warehouse B sensors before I commit a large order?"*

```
<thinking>
Before trusting any sensor readings for a high-stakes commit, I need to
classify each device's reliability using health metrics and anomaly data.
</thinking>

Step 1 — search_knowledge_base("Naive Bayes conditional independence posterior probability features class")
→ Retrieved eq. 3.4–3.8: P(c | o₁:ₙ) ∝ P(c) × ∏ P(oᵢ | c)

Step 2 — expand_graph_by_ids([doc_id_1, doc_id_2])
→ Confirmed: diffuse prior for devices with short observation history (Ch.19 §19.1)

Step 3 — GET /devices/health-summary
→ 4 devices in Warehouse B:
   D-101: avg_confidence=0.88, observed_missing=0.05, configured_missing=0.04
   D-102: avg_confidence=0.51, observed_missing=0.21, configured_missing=0.06
   D-103: avg_confidence=0.91, observed_missing=0.03, configured_missing=0.04
   D-104: avg_confidence=0.79, observed_missing=0.08, configured_missing=0.07

Step 4 — GET /devices/anomalies
→ D-102 flagged: anomaly_count=9, anomaly_type=calibration_drift

Step 5 — GET /devices/D-102
→ noise_sigma=22.0, bias=4.5, status=active

Step 6 — Score each device:
   D-101: 0.88 × (1−0.01) × 1.0 = 0.871  → HIGH
   D-102: 0.51 × (1−0.15) × 0.6 = 0.260  → LOW  ⚠️ calibration drift + high missing
   D-103: 0.91 × (1−0.00) × 1.0 = 0.910  → HIGH
   D-104: 0.79 × (1−0.01) × 1.0 = 0.782  → MEDIUM

Result:
  data_trustworthy = False  (1 LOW device: D-102)
  low_reliability_device_count = 1

Warehouse B has 1 unreliable device (D-102 — calibration drift, bias=4.5).
Readings from D-102's locations should not be trusted without bias correction.
Recommend: exclude D-102 observations from the order commit calculation,
or run `bayesian-sensor-belief-updater` with reported_noise_sigma override for affected locations.
```

---

## Feeds Into

- `bayesian-sensor-belief-updater` — uses `reliability_class` to decide whether to trust raw observations
- `decision-confidence-estimator` — applies `-0.15` confidence penalty per LOW-reliability device found
- `signal-conflict-resolver` — uses `reliability_score` per device to weight-average conflicting readings
