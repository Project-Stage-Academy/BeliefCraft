---
name: supplier-reliability-aggregator
description: "Computes a posterior reliability score for a supplier by combining their static reliability_score with real purchase order delivery history using a Beta-Binomial Bayesian update. Use before issuing a new purchase order, comparing suppliers, or when the static score seems outdated. Questions like 'Can we trust SupplierX for Q4 orders?', 'Which supplier is most reliable right now?', 'Has supplier reliability changed recently?'"
version: "1.0"
tags: [supplier, reliability, bayesian, procurement, risk]
dependencies: []
---

# SKILL-IA-02 · Supplier Reliability Evidence Aggregator

## When to Use This Skill

Activate this skill when the user asks about:
- Whether a specific supplier is reliable enough for an upcoming order
- Comparing reliability across multiple suppliers before procurement
- Whether a supplier's static score reflects their recent delivery behaviour
- Questions like *"Is SupplierX reliable enough for our Q4 critical orders?"*
  or *"Which supplier has the best real delivery track record?"*

---

## Core Concept

The static `reliability_score` in the database is a prior belief — it was set
at onboarding and may be stale. This skill applies **Bayesian parameter learning
for binary distributions** (Ch.4 §4.2.1, *Algorithms for Decision Making*)
to update that prior with real delivery evidence.

Each completed PO is a Bernoulli trial: on-time = 1, late = 0.
The conjugate prior for a Bernoulli parameter is the **Beta distribution**:

```
Prior:     Beta(α₀, β₀)
Posterior: Beta(α₀ + s, β₀ + f)   where s = on-time deliveries, f = late deliveries
Mean:      α / (α + β)             (eq. 4.27)
```

The static `reliability_score` seeds the prior as pseudocounts:
```
α₀ = reliability_score × 10
β₀ = (1 − reliability_score) × 10
```

---

## Step-by-Step Execution

### Step 1: Retrieve the Beta-Binomial update formula from the knowledge base

```
search_knowledge_base(
    query="Bayesian parameter learning binary distribution Beta prior posterior pseudocounts update",
    k=3
)
```

**What to extract from the result:**
- Beta posterior update rule (Ch.4 §4.2.1, eq. 4.26):
  `posterior = Beta(α + n, β + m − n)` where `n` = successes, `m` = total trials
- Beta mean formula (eq. 4.27): `mean = α / (α + β)`
- Pseudocount interpretation: prior `α₀, β₀` behave like observed counts

---

### Step 2: Expand linked concepts for prior seeding and evidence weighting

```
expand_graph_by_ids(
    ids=[<ids from step 1>]
)
```

**What to extract from the result:**
- How to choose a prior from expert knowledge (Ch.4 §4.2.1):
  encode `reliability_score` as pseudocounts `α₀ = score × 10, β₀ = (1−score) × 10`
- How prior importance diminishes with more data: large `m` makes prior negligible

---

### Step 3: Fetch supplier metadata

```
GET /api/v1/smart-query/procurement/suppliers/{supplier_id}
```

**Fields to extract:** `reliability_score`, `region`, `name`

Seed the Beta prior:
```
α₀ = reliability_score × 10
β₀ = (1 − reliability_score) × 10
```

---

### Step 4: Fetch completed purchase orders for the supplier

```
GET /api/v1/smart-query/procurement/purchase-orders
    ?supplier_id=<supplier_id>
    &status_in=received,partial
```

**Fields to extract per PO:** `id`, `expected_at`, `status`

---

### Step 5: Fetch shipment arrival data per PO

For each PO returned in Step 4:

```
GET /api/v1/smart-query/procurement/purchase-orders/{purchase_order_id}
```

**Classify each PO:**
```
on_time = (arrived_at <= expected_at)   →  success (s += 1)
late    = (arrived_at >  expected_at)   →  failure (f += 1)
```

Apply **exponential recency decay** (λ = 0.05/day) so older deliveries
contribute less than recent ones:
```
weight_i = exp(−λ × days_since_delivery)
s_effective = Σ weight_i  for on-time deliveries
f_effective = Σ weight_i  for late deliveries
```

---

### Step 6: Compute Beta posterior

Using the formula from Step 1:

```
α_post = α₀ + s_effective
β_post = β₀ + f_effective

posterior_mean     = α_post / (α_post + β_post)          # eq. 4.27
n_effective        = s_effective + f_effective

# Lower credible bound (90th percentile) — conservative risk estimate
# Use Beta distribution quantile: credible_lower_90 = Beta.ppf(0.10, α_post, β_post)
```

**Evidence weight classification:**
```
n_effective >= 20  →  "strong"
n_effective >= 5   →  "moderate"
n_effective <  5   →  "weak"   (posterior dominated by prior — treat with caution)
```

---

### Step 7: Fetch pipeline summary for context

```
GET /api/v1/smart-query/procurement/pipeline-summary
    ?supplier_id=<supplier_id>
    &status_in=open,pending
```

**Fields to extract:** `open_po_count`, `total_remaining`, `next_expected_at_min`

Use this to flag if the supplier has many open unresolved commitments
that haven't yet generated delivery evidence.

---

### Step 8: Return result

| Field | Value |
|---|---|
| `posterior_mean_reliability` | Updated reliability score [0–1] |
| `credible_lower_90` | Conservative lower bound (10th percentile of posterior) |
| `sample_size_effective` | Effective number of deliveries after recency weighting |
| `evidence_weight` | `strong` / `moderate` / `weak` |
| `recency_adjusted_score` | Weighted posterior mean emphasizing recent deliveries |
| `open_po_count` | Number of open POs not yet resolved |
| `prior_reliability_score` | Original static score from DB (for comparison) |

---

## Failure Modes

| Situation | Behaviour |
|---|---|
| No completed POs found | Return prior mean only, `evidence_weight="weak"`, warning |
| All POs still open | Flag `insufficient_history=True`, return prior mean |
| `expected_at` missing on PO | Skip that PO from evidence, log warning |
| `n_effective < 5` | `evidence_weight="weak"` — posterior dominated by prior |

---

## Example Walkthrough

**User query:** *"Is SupplierX reliable enough to handle our Q4 critical component orders?"*

```
<thinking>
The static reliability_score may be stale. I need to update it with
real delivery evidence using Beta-Binomial Bayesian learning.
</thinking>

Step 1 — search_knowledge_base("Bayesian parameter learning binary Beta prior posterior pseudocounts")
→ Retrieved eq. 4.26–4.27: posterior = Beta(α+n, β+m−n), mean = α/(α+β)

Step 2 — expand_graph_by_ids([doc_id_1, doc_id_2])
→ Confirmed: seed prior from expert knowledge as pseudocounts

Step 3 — GET /suppliers/supplier-uuid-xyz
→ reliability_score=0.82, name="SupplierX"
→ α₀ = 8.2,  β₀ = 1.8

Step 4 — GET /purchase-orders?supplier_id=supplier-uuid-xyz&status_in=received,partial
→ 23 completed POs returned

Step 5 — Classify deliveries with recency decay:
→ 17 on-time (s_effective = 14.3 after decay)
→  6 late    (f_effective =  5.1 after decay)

Step 6 — Compute posterior:
    α_post = 8.2 + 14.3 = 22.5
    β_post = 1.8 +  5.1 =  6.9
    posterior_mean  = 22.5 / (22.5 + 6.9) = 0.765
    credible_lower_90 = Beta.ppf(0.10, 22.5, 6.9) = 0.634
    evidence_weight = "strong"  (n_effective=19.4)

Step 7 — GET /pipeline-summary?supplier_id=supplier-uuid-xyz
→ open_po_count=3, next_expected_at_min="2026-04-01"

Result:
  posterior_mean_reliability = 0.765   (was 0.82 static)
  credible_lower_90          = 0.634
  evidence_weight            = "strong"

SupplierX's real reliability (0.77) is lower than their static score (0.82).
6 late deliveries in recent history are pulling the score down.
For critical Q4 orders, consider requesting a delivery commitment with
penalty clauses given the 63% conservative lower bound.
```

---

## Feeds Into

- `SKILL-RE-02` — uses `posterior_mean_reliability` to inflate lead-time variance
- `SKILL-PU-01` — uses `posterior_mean_reliability` as `u_sla` input for utility scoring
- `SKILL-DS-01` — used in tie-breaking when two suppliers have equal utility scores