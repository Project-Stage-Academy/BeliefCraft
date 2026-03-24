---
name: threshold-based-trigger-decision
description: "Evaluates the current inventory state against a hierarchy of threshold conditions and returns a typed trigger event — STOCKOUT_IMMINENT, REORDER_TRIGGER, PIPELINE_RISK, or NORMAL — with a recommended action type. Use as the entry-point classifier before deeper decision logic; the trigger event constrains the action space for all downstream skills. Questions like 'Do we need to act on SKU-X right now?', 'Is the inventory level critical?', 'What kind of event is this — reorder or emergency?'"
version: "1.0"
tags: [threshold, trigger, inventory, stockout, reorder, policy, safety-stock]
dependencies:
  - bayesian-sensor-belief-updater
---

# Threshold-Based Trigger Decision

## When to Use This Skill

Activate this skill when the user asks about:
- Whether current inventory levels require immediate action
- What type of inventory event is occurring right now
- Which response is appropriate — emergency order, standard reorder, monitor, or do nothing
- As the first step in any decision pipeline to classify urgency before scoring
- Questions like *"Is SKU-3301 in a critical state?"* or *"Do we need to act today?"*
  or *"What kind of inventory event is this?"*

---

## Core Concept

For problems with a scalar state (inventory level), the optimal policy from
a value function takes the form of a **threshold policy**: compare the current
state to a set of breakpoints and select the action associated with the region
the state falls in (Ch.7 §7.3, Ch.14 §14.1, *Algorithms for Decision Making*).

The greedy policy extracted from a value function U is (eq. 7.11):

```
π(s) = argmax_a [ R(s,a) + γ Σ_{s'} T(s'|s,a) U(s') ]     (eq. 7.11)
```

For inventory, this collapses to comparing `available_qty` against pre-computed
threshold breakpoints. This is the "simple heuristic policy parameterised by
thresholds" described in Example 14.1 of Ch.14 §14.1 — a practical
approximation to the full dynamic programming solution that is optimal
when the state space is one-dimensional and the reward is monotone.

Four threshold regions partition the state space into four trigger events:

```
State s = available_qty (posterior mean from `bayesian-sensor-belief-updater`)

s < safety_stock  AND  days_of_cover < 3   →  STOCKOUT_IMMINENT   (CRITICAL)
s < safety_stock  OR   days_of_cover < 7   →  REORDER_TRIGGER     (HIGH)
effective_cover   < 14 AND pipeline_qty < safety_stock  →  PIPELINE_RISK  (MEDIUM)
otherwise                                   →  NORMAL              (LOW)
```

---

## Step-by-Step Execution

### Step 1: Retrieve threshold policy definition from knowledge base

```
search_knowledge_base(
    query="threshold policy value function greedy state action region breakpoint simple policy parameterised",
    k=3
)
```

**What to extract from the result:**
- Ch.7 §7.3, eq. 7.11 — greedy policy: `π(s) = argmax_a [R(s,a) + γ Σ T(s'|s,a) U(s')]`
  The greedy policy with respect to U is the optimal response at each state.
- Ch.14 §14.1, Example 14.1 — "simple heuristic policy parameterised by thresholds":
  if `|h| < h_thresh AND t_col < t_thresh` then issue advisory.
  Warehouse analogue: if `qty < threshold AND cover < days_threshold` then trigger action.
- Key insight: threshold policies are optimal when the value function is
  monotone in the state variable — inventory level satisfies this condition.

---

### Step 2: Retrieve lookahead equation for the policy basis

```
get_entity_by_number(number="7.11")
```

**What to extract from the result:**
- Exact form of eq. 7.11: `π(s) = argmax_a [R(s,a) + γ Σ_{s'} T(s'|s,a) U(s')]`
- This is the general form; for the warehouse the threshold breakpoints
  approximate the argmax by partitioning the state into regions where
  each action (EMERGENCY_ORDER, PLACE_ORDER, MONITOR, etc.) is dominant.
- Confirms: threshold conditions are a tractable realisation of greedy
  policy extraction when full dynamic programming is not available.

---

### Step 3: Get posterior inventory level from `bayesian-sensor-belief-updater`

Requires `posterior_mean` (μ) from `bayesian-sensor-belief-updater`.
This is the best current estimate of true on-hand quantity.

```
available_qty = posterior_mean   # from bayesian-sensor-belief-updater
```

If `bayesian-sensor-belief-updater` was not run, fall back to raw `observed_qty` from the
observed-snapshot endpoint (less reliable):

```
GET /api/v1/smart-query/inventory/observed-snapshot
    ?product_id=<product_id>
    &location_id=<location_id>
```

**Fields to extract:** `observed_qty`, `confidence`, `quality_status`

---

### Step 4: Fetch recent demand rate from inventory moves

```
GET /api/v1/smart-query/inventory/moves
    ?product_id=<product_id>
    &move_type=outbound
    &from_ts=<now - 30 days>
    &to_ts=<now>
```

**Fields to extract:** `qty` per move, `occurred_at`

```
# Daily demand rate (30-day average)
total_outbound_30d = sum(move.qty for move in moves)
daily_demand       = total_outbound_30d / 30.0

# Days of cover from current stock only
days_of_cover = available_qty / max(daily_demand, 0.01)
```

---

### Step 5: Fetch inbound pipeline from procurement

```
GET /api/v1/smart-query/procurement/pipeline-summary
    ?product_id=<product_id>
    &status_in=open,pending
```

**Fields to extract:** `total_remaining`, `next_expected_at_min`

```
pipeline_qty    = total_remaining
next_arrival_at = next_expected_at_min

# Effective coverage including inbound pipeline
effective_cover = (available_qty + pipeline_qty) / max(daily_demand, 0.01)

# Days until next arrival
days_to_arrival = (next_arrival_at - now).days   # if available
```

---

### Step 6: Determine safety stock threshold

Safety stock is the minimum buffer qty below which action is required.
Derive from configuration or compute as:

```
# Conservative default: 7 days of demand
safety_stock = 7 × daily_demand

# Override with product-level config if available from:
GET /api/v1/smart-query/topology/locations/{location_id}
# field: min_stock_level (if present)
```

---

### Step 7: Classify trigger event

Apply threshold policy (greedy policy approximation from Steps 1–2):

```
# Threshold 1 — STOCKOUT_IMMINENT: stock below safety AND cover < 3 days
if available_qty < safety_stock AND days_of_cover < 3:
    trigger_event           = STOCKOUT_IMMINENT
    severity                = CRITICAL
    recommended_action_type = EMERGENCY_ORDER

# Threshold 2 — REORDER_TRIGGER: below safety OR cover < 7 days
elif available_qty < safety_stock OR days_of_cover < 7:
    trigger_event           = REORDER_TRIGGER
    severity                = HIGH
    recommended_action_type = PLACE_ORDER

# Threshold 3 — PIPELINE_RISK: pipeline thin relative to demand horizon
elif effective_cover < 14 AND pipeline_qty < safety_stock:
    trigger_event           = PIPELINE_RISK
    severity                = MEDIUM
    recommended_action_type = EXPEDITE_OR_MONITOR

# Threshold 4 — NORMAL: all conditions satisfied
else:
    trigger_event           = NORMAL
    severity                = LOW
    recommended_action_type = MONITOR
```

---

### Step 8: Return result

| Field | Value |
|---|---|
| `trigger_event` | `STOCKOUT_IMMINENT` / `REORDER_TRIGGER` / `PIPELINE_RISK` / `NORMAL` |
| `severity` | `CRITICAL` / `HIGH` / `MEDIUM` / `LOW` |
| `available_qty` | Posterior mean inventory (from `bayesian-sensor-belief-updater` or observed_qty) |
| `safety_stock` | Threshold used for comparison |
| `daily_demand` | 30-day average daily demand rate |
| `days_of_cover` | `available_qty / daily_demand` |
| `pipeline_qty` | Total inbound qty from open/pending POs |
| `effective_coverage` | `(available_qty + pipeline_qty) / daily_demand` |
| `days_to_next_arrival` | Days until next PO expected (if available) |
| `recommended_action_type` | `EMERGENCY_ORDER` / `PLACE_ORDER` / `EXPEDITE_OR_MONITOR` / `MONITOR` |
| `ia01_used` | `true` if `bayesian-sensor-belief-updater` posterior was used, `false` if raw observed_qty |

---

## Failure Modes

| Situation | Behaviour |
|---|---|
| `bayesian-sensor-belief-updater` not run, no observed snapshot | Return `trigger_event=NORMAL`, `data_gap_flag=True`, escalate |
| `daily_demand = 0` (no recent moves) | Set `days_of_cover = ∞`, skip cover thresholds, classify by qty vs safety_stock only |
| Pipeline endpoint unavailable | Set `pipeline_qty = 0`, `effective_cover = days_of_cover`, add warning |
| `quality_status` is `quarantine` or `damaged` | Override: treat `available_qty = 0` for threshold purposes, add `quality_hold_flag=True` |
| Safety stock config missing | Use default `7 × daily_demand`; log that default was applied |

---

## Example Walkthrough

**User query:** *"What's the inventory situation for SKU-8801 in Warehouse A — do we need to act?"*

```
<thinking>
I need to evaluate the current state against threshold breakpoints
and return a typed trigger event. This is a threshold policy applied
to a single-state inventory variable.
</thinking>

Step 1 — search_knowledge_base("threshold policy value function greedy state action region breakpoint simple policy parameterised")
→ Retrieved: Ch.7 §7.3 eq. 7.11 — greedy policy π(s) = argmax_a [R(s,a) + γΣT U(s')]
→ Retrieved: Ch.14 §14.1 Example 14.1 — threshold heuristic:
  "if |h| < h_thresh AND t_col < t_thresh then issue advisory"
  Warehouse analogue: compare qty and cover against threshold breakpoints

Step 2 — get_entity_by_number(number="7.11")
→ Retrieved: π(s) = argmax_a [R(s,a) + γ Σ_{s'} T(s'|s,a) U(s')]
→ Confirmed: threshold conditions partition the state into regions where
  each action is dominant — tractable approximation to full DP greedy policy

Step 3 — `bayesian-sensor-belief-updater` result:
    posterior_mean = 142.0 units
    available_qty  = 142.0   (ia01_used = true)

Step 4 — GET /inventory/moves?product_id=SKU-8801&move_type=outbound&from_ts=30d
    total_outbound_30d = 840 units
    daily_demand       = 840 / 30 = 28.0 units/day
    days_of_cover      = 142 / 28 = 5.07 days

Step 5 — GET /pipeline-summary?product_id=SKU-8801&status_in=open,pending
    total_remaining  = 200 units
    next_expected_at = 2026-03-15  (3 days from now)
    pipeline_qty     = 200
    effective_cover  = (142 + 200) / 28 = 12.2 days

Step 6 — Safety stock:
    safety_stock = 7 × 28 = 196 units

Step 7 — Classify trigger:
    Threshold 1: available_qty(142) < safety_stock(196)?  ✓
                 days_of_cover(5.07) < 3?  ✗
                 → NOT STOCKOUT_IMMINENT

    Threshold 2: available_qty(142) < safety_stock(196)?  ✓
                 → REORDER_TRIGGER

    trigger_event           = REORDER_TRIGGER
    severity                = HIGH
    recommended_action_type = PLACE_ORDER

Result:
  trigger_event      = REORDER_TRIGGER
  severity           = HIGH
  available_qty      = 142 units
  safety_stock       = 196 units
  days_of_cover      = 5.1 days
  effective_coverage = 12.2 days
  pipeline_qty       = 200 units
  days_to_arrival    = 3 days

SKU-8801 is below safety stock (142 vs 196 units) with only 5 days of cover.
A reorder is warranted. The inbound pipeline (200 units, arriving in 3 days)
provides moderate relief — effective coverage reaches 12.2 days — but stock
will be below safety threshold until the shipment arrives.
Recommended action: PLACE_ORDER with expedite option if lead time allows.
```

---

## Feeds Into

- `decision-deferral-controller` — `STOCKOUT_IMMINENT` bypasses deferral controller entirely;
  deferral is never permitted when trigger is CRITICAL
- `expected-utility-action-ranker` — `trigger_event` constrains the action space:
  `STOCKOUT_IMMINENT` restricts candidates to `EMERGENCY_ORDER` actions only
- `decision-confidence-estimator` — `severity` contributes to composite confidence score;
  `CRITICAL` overrides normal confidence thresholds
- `multi-attribute-utility-scorer` — `days_of_cover` feeds `u_fill` calculation as a proxy
  for forward fill risk when order line qty is unavailable
