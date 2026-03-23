---
name: leadtime-risk-estimator
description: "Estimates statistical lead-time risk for a purchase order by fitting a mixture distribution over the base delivery time and rare delay scenarios, then inflating variance based on supplier reliability. Returns expected lead time, P95/P99 quantiles, and probability of exceeding a planning horizon. Use before issuing a PO, comparing suppliers on delivery risk, or stress-testing replenishment plans. Questions like 'Will this supplier deliver on time?', 'What is the worst-case lead time for this order?', 'How likely is a delay beyond 14 days?'"
version: "1.0"
tags: [lead-time, risk, supplier, procurement, mixture-distribution, quantile]
dependencies:
  - supplier-reliability-aggregator
---

# Lead-Time Risk Estimator

## When to Use This Skill

Activate this skill when the user asks about:
- Probability that a supplier will deliver within a target date
- Worst-case or tail lead times (P95, P99) for procurement planning
- How supplier reliability affects delivery variance
- Stress-testing a replenishment plan against delayed deliveries
- Questions like *"What's the realistic worst-case delivery time from SupplierX?"*
  or *"How likely is a delay beyond our 14-day planning horizon?"*

---

## Core Concept

Lead time is not deterministic. The `leadtime_models` table stores a parametric
base distribution (`dist_family`, `p1`, `p2`) and a rare-delay component
(`p_rare_delay`, `rare_delay_add_days`). Together they form a **mixture distribution**
(Ch.2 §2.3, eq. 2.17, *Algorithms for Decision Making*):

```
p(LT) = (1 − ρ) × F_base(p1, p2) + ρ × F_shifted(p1, p2 + rare_delay_add_days)
```

where `ρ = p_rare_delay`. This captures both normal delivery and occasional
severe delays in a single model.

Supplier reliability from `supplier-reliability-aggregator` then inflates the mixture variance:
```
Var[LT]_adjusted = Var[LT]_base × (1 + (1 − reliability))
```
— a robustness adjustment that penalises unreliable suppliers (Ch.14 §14.3).

---

## Step-by-Step Execution

### Step 1: Retrieve mixture distribution formula from knowledge base

```
search_knowledge_base(
    query="mixture distribution weighted sum components Gaussian mixture density probability",
    k=3
)
```

**What to extract from the result:**
- Mixture density formula (Ch.2 §2.3, eq. 2.17):
  `p(x) = Σ ρᵢ × N(x | μᵢ, σᵢ²)`
- Weights must sum to 1: `(1 − ρ) + ρ = 1`
- How to compute mean and variance of a mixture:
  `E[X] = Σ ρᵢ × μᵢ`
  `Var[X] = Σ ρᵢ × (σᵢ² + μᵢ²) − E[X]²`

---

### Step 2: Retrieve quantile function definition

```
get_entity_by_number(number="2.4")
```

**What to extract from the result:**
- Quantile function definition (Ch.2, figure 2.4):
  `quantile_X(α)` = value x such that `P(X ≤ x) = α`
- Use `α=0.95` for P95 and `α=0.99` for P99 lead-time estimates
- Tail exceedance probability: `P(LT > horizon) = 1 − CDF(horizon)`

---

### Step 3: Retrieve robustness / variance inflation concept

```
search_knowledge_base(
    query="robustness modeling errors sensitivity policy evaluation deviation uncertainty inflation",
    k=2
)
```

**What to extract from the result:**
- Ch.14 §14.3 — robustness analysis: evaluate policies under model deviations
- Apply supplier unreliability as a perturbation to the variance parameter:
  `Var_adjusted = Var_base × (1 + (1 − reliability))`
  — less reliable supplier → wider distribution → higher P95/P99

---

### Step 4: Fetch leadtime model for the purchase order

```
GET /api/v1/smart-query/procurement/purchase-orders/{purchase_order_id}
```

Extract `leadtime_model_id`.

Then fetch the model parameters:

```
GET /api/v1/smart-query/procurement/pipeline-summary
    ?supplier_id=<supplier_id>
```

From `leadtime_models` via the PO record extract:
`dist_family`, `p1`, `p2`, `p_rare_delay`, `rare_delay_add_days`

**Fallback:** if no `leadtime_model_id` on the PO → fetch the global-scope
leadtime model:

```
GET /api/v1/smart-query/procurement/pipeline-summary
    ?scope=global
```

---

### Step 5: Fetch supplier reliability from `supplier-reliability-aggregator`

Requires `posterior_mean_reliability` from `supplier-reliability-aggregator` output for this supplier.

If `supplier-reliability-aggregator` was not run, use `suppliers.reliability_score` as a fallback.

---

### Step 6: Build mixture distribution and compute risk metrics

Using the formula from Step 1 and quantile definition from Step 2:

```
# 1. Base distribution parameters
#    dist_family ∈ {normal, gamma, lognormal}
#    p1 = mean (or shape), p2 = std (or scale)

# 2. Shifted distribution for rare delay component
#    same dist_family but mean shifted by rare_delay_add_days

# 3. Mixture weights
w_base  = 1 − p_rare_delay
w_delay = p_rare_delay

# 4. Mixture mean (eq. 2.17 applied to means)
E[LT] = w_base × p1 + w_delay × (p1 + rare_delay_add_days)

# 5. Mixture variance (law of total variance)
Var_base    = p2²
Var_shifted = p2²
Var_mixture = w_base × (Var_base + p1²) + w_delay × (Var_shifted + (p1 + rare_delay_add_days)²) − E[LT]²

# 6. Reliability inflation (Ch.14 §14.3 robustness perturbation)
reliability = posterior_mean_reliability  (from `supplier-reliability-aggregator`)
Var_adjusted = Var_mixture × (1 + (1 − reliability))
σ_adjusted   = sqrt(Var_adjusted)

# 7. Quantiles (Ch.2 figure 2.4 — inverse CDF of adjusted mixture)
P95 = mixture_quantile(α=0.95, weights, dist_family, p1, p2, rare_delay, reliability)
P99 = mixture_quantile(α=0.99, ...)

# 8. Tail exceedance probability for planning horizon
P(LT > horizon) = 1 − mixture_CDF(horizon)

# 9. Risk classification
risk_class = ACCEPTABLE  if P(LT > horizon) < 0.05
             ELEVATED    if P(LT > horizon) < 0.20
             CRITICAL    if P(LT > horizon) ≥ 0.20
```

---

### Step 7: Return result

| Field | Value |
|---|---|
| `expected_lead_time_days` | Mixture mean E[LT] |
| `variance_lead_time` | Reliability-adjusted variance |
| `p95_lead_time` | 95th percentile of adjusted mixture |
| `p99_lead_time` | 99th percentile of adjusted mixture |
| `prob_exceed_horizon` | P(LT > planning_horizon) |
| `risk_class` | `ACCEPTABLE` / `ELEVATED` / `CRITICAL` |
| `reliability_used` | Reliability score used for variance inflation |
| `rare_delay_contribution` | Weight of the rare-delay component (`p_rare_delay`) |

---

## Failure Modes

| Situation | Behaviour |
|---|---|
| No `leadtime_model_id` on PO | Fall back to global-scope model, add warning |
| `supplier-reliability-aggregator` result unavailable | Use static `reliability_score`, `evidence_weight="weak"` |
| `p_rare_delay = 0` | Single-component distribution, no mixture needed |
| `dist_family` not recognised | Default to normal distribution, add warning |
| `prob_exceed_horizon` unavailable (no horizon given) | Omit field, return quantiles only |

---

## Example Walkthrough

**User query:** *"We need SupplierX to deliver within 10 days for this critical order — what's the actual risk?"*

```
<thinking>
I need to model the full lead-time distribution including rare delays,
inflated by SupplierX's actual reliability, then compute P(LT > 10).
</thinking>

Step 1 — search_knowledge_base("mixture distribution weighted sum components density probability")
→ Retrieved eq. 2.17: p(x) = Σ ρᵢ × N(x | μᵢ, σᵢ²)
→ E[X] = Σ ρᵢ × μᵢ,  Var[X] = Σ ρᵢ(σᵢ² + μᵢ²) − E[X]²

Step 2 — get_entity_by_number(number="2.4")
→ Retrieved: quantile_X(α) = x such that P(X ≤ x) = α
→ P(LT > horizon) = 1 − CDF(horizon)

Step 3 — search_knowledge_base("robustness modeling errors sensitivity variance inflation")
→ Retrieved: Ch.14 §14.3 — Var_adjusted = Var_base × (1 + deviation_factor)

Step 4 — GET /purchase-orders/po-uuid-abc → leadtime_model_id = LM-07
→ dist_family=normal, p1=7.0, p2=1.5, p_rare_delay=0.12, rare_delay_add_days=8

Step 5 — `supplier-reliability-aggregator` result:
→ posterior_mean_reliability = 0.765

Step 6 — Compute:
    E[LT]       = 0.88 × 7.0 + 0.12 × 15.0 = 7.96 days
    Var_mixture = 0.88×(2.25+49) + 0.12×(2.25+225) − 7.96²
                = 45.1 + 27.3 − 63.4 = 9.0
    Var_adjusted= 9.0 × (1 + 0.235) = 11.1   (reliability=0.765)
    σ_adjusted  = 3.33 days
    P95         = 7.96 + 1.645 × 3.33 ≈ 13.4 days
    P99         = 7.96 + 2.326 × 3.33 ≈ 15.7 days
    P(LT > 10)  = 1 − Φ((10 − 7.96) / 3.33) = 1 − Φ(0.61) ≈ 0.27

    risk_class = CRITICAL  (P(LT > 10) = 27% ≥ 20%)

Result:
  expected_lead_time_days = 7.96
  p95_lead_time           = 13.4 days
  p99_lead_time           = 15.7 days
  prob_exceed_horizon     = 0.27
  risk_class              = CRITICAL

There is a 27% chance SupplierX misses the 10-day deadline.
Recommend: either select an alternative supplier with lower P(LT > 10),
or place the order now with 6+ days buffer to absorb the tail risk.
```

---

## Feeds Into

- `multi-attribute-utility-scorer` — uses `risk_class` as `u_lt` factor in utility scoring
- `decision-confidence-estimator` — uses `risk_class` in decision confidence assessment
- `stochastic-dominance-filter` — uses full distribution for stochastic dominance comparison across suppliers
- `threshold-based-trigger-decision` — uses `expected_lead_time_days` for pipeline coverage calculation
