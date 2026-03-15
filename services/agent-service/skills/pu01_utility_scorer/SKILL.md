---
name: multi-attribute-utility-scorer
description: "Scores candidate actions (replenishment orders, allocations, supplier selections) by computing a weighted multi-attribute utility that combines fill rate, penalty exposure, lead-time risk, and SLA priority into a single comparable scalar. Use before ranking actions or selecting the best option. Questions like 'Which replenishment action is best overall?', 'How good is this allocation decision?', 'Score these three supplier options.'"
version: "1.0"
tags: [utility, decision, multi-attribute, expected-utility, MEU, ranking]
dependencies: [SKILL-IA-02, SKILL-RE-02]
---

# SKILL-PU-01 · Multi-Attribute Utility Scorer

## When to Use This Skill

Activate this skill when the user asks about:
- Which of several candidate actions is the best overall choice
- Scoring a replenishment order, allocation, or supplier selection
- Combining multiple competing objectives (fill rate, penalties, lead time, SLA) into one score
- As input to `SKILL-DS-01` before final action ranking
- Questions like *"Which supplier option scores best given our priorities?"*
  or *"How good is this replenishment plan compared to the alternatives?"*

---

## Core Concept

A rational agent chooses the action that maximises **expected utility**
(Ch.6 §6.4, *Algorithms for Decision Making*, eq. 6.7–6.8):

```
EU(a | o) = Σ P(s' | a, o) × U(s')        (eq. 6.7)
a*         = argmax_a EU(a | o)             (eq. 6.8)
```

For warehouse decisions, the utility of an action is a **normalised weighted
sum** over four attributes (Ch.6 §6.2 — normalised utility, best=1, worst=0):

```
U(a) = w_fill × u_fill + w_penalty × u_penalty + w_lt × u_lt + w_sla × u_sla
```

Default weights (configurable): `w_fill=0.35, w_penalty=0.30, w_lt=0.20, w_sla=0.15`

---

## Step-by-Step Execution

### Step 1: Retrieve utility function and MEU principle from knowledge base

```
search_knowledge_base(
    query="utility function expected utility maximisation rational decision weighted attributes normalised",
    k=3
)
```

**What to extract from the result:**
- Normalised utility definition (Ch.6 §6.2): best outcome = 1, worst = 0,
  all others scaled linearly in between
- Utility of a lottery (eq. 6.2): `U([S₁:p₁; …; Sₙ:pₙ]) = Σ pᵢ U(Sᵢ)`
- MEU principle (eq. 6.7–6.8):
  `EU(a|o) = Σ P(s'|a,o) U(s')`,  `a* = argmax_a EU(a|o)`

---

### Step 2: Retrieve exact equation numbers for utility elicitation

```
get_entity_by_number(number="6.7")
```

**What to extract from the result:**
- Exact form of `EU(a | o)` and how it maps to a weighted attribute sum
  when outcomes are factored across independent attributes

```
get_entity_by_number(number="6.2")
```

**What to extract from the result:**
- Lottery utility formula — used to verify that the weighted attribute sum
  is a valid expected utility representation when attributes are independent

---

### Step 3: Fetch order line data

```
GET /api/v1/smart-query/procurement/purchase-orders/{purchase_order_id}
```

or for outbound allocation:

```
GET /api/v1/smart-query/orders/{order_id}
```

**Fields to extract:** `qty_ordered`, `qty_allocated`, `qty_shipped`,
`service_level_penalty`, `sla_priority`, `promised_at`, `status`

---

### Step 4: Compute each attribute utility component

Using the normalised utility from Step 1 (best=1, worst=0):

```
# u_fill — fill rate utility (piecewise linear, Ch.6 §6.2 normalised)
fill_rate = qty_allocated / max(qty_ordered, 1)
u_fill    = fill_rate                          # 0 = no fill, 1 = full fill

# u_penalty — penalty exposure utility (inverse of penalty risk)
# service_level_penalty is the cost per unit short
penalty_exposure = service_level_penalty × max(qty_ordered - qty_allocated, 0)
u_penalty = 1 / (1 + penalty_exposure / 1000)  # normalised: high penalty → low utility

# u_lt — lead-time risk utility (from SKILL-RE-02 risk_class)
u_lt = 1.0   if risk_class = ACCEPTABLE
       0.6   if risk_class = ELEVATED
       0.2   if risk_class = CRITICAL
       1.0   if SKILL-RE-02 not available (no lead-time uncertainty)

# u_sla — SLA priority utility (direct normalisation of sla_priority)
# sla_priority is typically 1 (highest) to 5 (lowest)
u_sla = (max_priority - sla_priority) / (max_priority - 1)
        # e.g. priority=1 → u_sla=1.0,  priority=5 → u_sla=0.0

# Weighted sum (configurable weights, must sum to 1)
U(a) = 0.35 × u_fill + 0.30 × u_penalty + 0.20 × u_lt + 0.15 × u_sla
```

---

### Step 5: Identify dominant driver

```
dominant_driver = attribute with highest weighted contribution:
    argmax({ 0.35×u_fill, 0.30×u_penalty, 0.20×u_lt, 0.15×u_sla })
```

---

### Step 6: Return result

| Field | Value |
|---|---|
| `action_utility_score` | Weighted utility U(a) ∈ [0, 1] |
| `utility_breakdown` | `{u_fill, u_penalty, u_lt, u_sla}` — individual components |
| `dominant_driver` | Attribute contributing most to the score |
| `normalized_rank` | Rank among scored candidates (if multiple actions passed) |
| `weights_used` | `{w_fill, w_penalty, w_lt, w_sla}` — for auditability |

---

## Failure Modes

| Situation | Behaviour |
|---|---|
| `SKILL-RE-02` not run | `u_lt=1.0`, add warning that lead-time risk is not accounted for |
| `qty_ordered = 0` | `u_fill=1.0` (trivially satisfied), add warning |
| `service_level_penalty` missing | `u_penalty=0.5` (neutral), add warning |
| `sla_priority` missing | `u_sla=0.5` (neutral), add warning |
| All weights sum ≠ 1 | Normalise weights before scoring, log adjustment |

---

## Example Walkthrough

**User query:** *"We have three possible replenishment orders for SKU-9901 — which one scores best overall?"*

```
<thinking>
I need to score each candidate action on fill rate, penalty exposure,
lead-time risk, and SLA priority, then combine into a single utility score.
</thinking>

Step 1 — search_knowledge_base("utility function expected utility maximisation rational decision weighted attributes normalised")
→ Retrieved eq. 6.2: U([S₁:p₁;…]) = Σ pᵢU(Sᵢ)
→ Retrieved eq. 6.7–6.8: EU(a|o) = Σ P(s'|a,o)U(s'), a* = argmax EU(a|o)
→ Normalised utility: best=1, worst=0

Step 2 — get_entity_by_number(number="6.7")
→ Confirmed: EU(a|o) maps to weighted attribute sum when attributes independent

        get_entity_by_number(number="6.2")
→ Confirmed: lottery utility = weighted sum of outcome utilities

Step 3 — GET /purchase-orders for three candidate POs:
    Action A: qty_ordered=500, qty_allocated=480, sla_priority=1, service_level_penalty=20
    Action B: qty_ordered=500, qty_allocated=350, sla_priority=2, service_level_penalty=20
    Action C: qty_ordered=300, qty_allocated=300, sla_priority=3, service_level_penalty=5

Step 4 — SKILL-RE-02 results: A=ELEVATED, B=ACCEPTABLE, C=ACCEPTABLE

Compute utilities:
    Action A: u_fill=0.96, u_penalty=1/(1+400)=0.002, u_lt=0.6,  u_sla=1.0
              U(A) = 0.35×0.96 + 0.30×0.002 + 0.20×0.6 + 0.15×1.0 = 0.336+0.001+0.12+0.15 = 0.607

    Action B: u_fill=0.70, u_penalty=1/(1+3000)=0.0003, u_lt=1.0, u_sla=0.75
              U(B) = 0.35×0.70 + 0.30×0.0003 + 0.20×1.0 + 0.15×0.75 = 0.245+0+0.20+0.113 = 0.558

    Action C: u_fill=1.00, u_penalty=1/(1+0)=1.0, u_lt=1.0, u_sla=0.5
              U(C) = 0.35×1.0 + 0.30×1.0 + 0.20×1.0 + 0.15×0.5 = 0.35+0.30+0.20+0.075 = 0.925

Step 5 — dominant_driver for C: u_penalty (0.30 weighted contribution)

Result:
  Action C: U=0.925  ← best
  Action A: U=0.607
  Action B: U=0.558

Action C scores highest despite smaller quantity — full fill with zero
penalty exposure and low lead-time risk outweighs Action A's higher fill count.
Recommend Action C. Note: if volume is a hard requirement, escalate to
SKILL-PU-03 to check capacity constraints before committing.
```

---

## Feeds Into

- `SKILL-DS-01` — uses `action_utility_score` to rank and select best action
- `SKILL-DS-02` — uses `utility_breakdown` for stochastic dominance filtering
- `SKILL-PU-02` — uses best `action_utility_score` as baseline EU for VOI calculation
- `SKILL-MD-01` — uses scores spread to compute decision margin
