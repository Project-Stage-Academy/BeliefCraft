---
name: constraint-satisfaction-validator
description: "Validates whether a proposed warehouse action (replenishment, allocation, transfer) satisfies all hard physical and operational constraints before execution: capacity, quality status, shelf life, and allocation bounds. Blocks INFEASIBLE actions before they reach the utility scorer. Use as a pre-filter before SKILL-PU-01 or before committing any warehouse operation. Questions like 'Can we physically fit this order in Warehouse B?', 'Is this stock eligible for outbound shipment?', 'Will this allocation exceed our committed quantities?'"
version: "1.0"
tags: [constraint, feasibility, capacity, quality, allocation, validation]
dependencies: []
---

# SKILL-PU-03 · Constraint Satisfaction Validator

## When to Use This Skill

Activate this skill when the user asks about:
- Whether a proposed action is physically possible given warehouse capacity
- Whether stock quality status allows outbound shipment
- Whether an allocation exceeds committed order quantities
- As a mandatory pre-filter before scoring actions in `SKILL-PU-01`
- Questions like *"Can Warehouse B physically hold this replenishment order?"*
  or *"Is this stock eligible for the customer shipment?"*

---

## Core Concept

Rational agents only choose from **feasible** actions — those that satisfy
all hard constraints on the outcome space (Ch.6 §6.1, *Algorithms for
Decision Making*). Before computing utility, infeasible actions must be
eliminated from the candidate set.

Hard constraints are **absolute** — any violation makes the action infeasible
regardless of its utility score. Soft constraints produce a penalty score
but do not block the action outright.

From Ch.14 §14.3 (Robustness Analysis): evaluate actions under
plausible deviations from the nominal model — e.g. capacity calculations
should account for already-reserved stock, not just on-hand quantities.

---

## Step-by-Step Execution

### Step 1: Retrieve constraint framework from knowledge base

```
search_knowledge_base(
    query="rational preferences constraints feasibility action space completeness transitivity",
    k=3
)
```

**What to extract from the result:**
- Ch.6 §6.1 — Constraints on Rational Preferences:
  rational agent requires **completeness** (every outcome is comparable)
  and **transitivity** — infeasible outcomes must be excluded before
  preference ordering is applied
- Hard constraint principle: an action is only admissible if it lies
  within the feasible region of the outcome space

---

### Step 2: Retrieve robustness / stress-test framing for capacity check

```
get_entity_by_number(number="14.3")
```

**What to extract from the result:**
- Ch.14 §14.3 — Robustness Analysis: evaluate action under plausible
  deviations — use `on_hand + reserved` (not just `on_hand`) as the
  conservative capacity baseline to avoid overcommitment
- Stress-test boundary: if capacity utilisation > 0.9 (endpoint unavailable
  fallback), treat as at-risk and return CONDITIONAL rather than FEASIBLE

---

### Step 3: Fetch warehouse capacity utilisation

```
GET /api/v1/smart-query/topology/warehouses/{warehouse_id}/capacity-utilization
```

**Fields to extract:** `used_capacity_units`, `total_capacity_units`,
`utilization_rate`, `location_id`

Compute remaining capacity:
```
remaining_capacity = total_capacity_units − used_capacity_units
```

**Fallback:** if endpoint unavailable → assume `utilization_rate = 0.9`
(conservative stress-test default per Ch.14 §14.3)

---

### Step 4: Fetch inventory balance and quality status

```
GET /api/v1/smart-query/inventory/observed-snapshot
    ?product_id=<product_id>
    &location_id=<location_id>
```

**Fields to extract:** `on_hand`, `reserved`, `quality_status`, `last_count_at`

Also fetch product shelf-life if applicable:
```
GET /api/v1/smart-query/topology/locations/{location_id}
```

**Fields to extract:** `capacity_units`, `type`

---

### Step 5: Fetch order line for allocation bounds

```
GET /api/v1/smart-query/orders/{order_id}
```

**Fields to extract per line:** `qty_ordered`, `qty_allocated`, `qty_shipped`

---

### Step 6: Evaluate hard constraints

Using the feasibility principle from Step 1:

```
# Hard Constraint 1 — Capacity
capacity_ok = (on_hand + qty_proposed) <= total_capacity_units
violation_1 = None if capacity_ok else "CAPACITY_EXCEEDED"

# Hard Constraint 2 — Quality (outbound shipments only)
quality_ok  = quality_status in ('good', 'verified')
violation_2 = None if quality_ok else f"QUALITY_BLOCKED: {quality_status}"

# Hard Constraint 3 — Shelf Life (if shelf_life_days available)
days_remaining = (expiry_date - today).days   # if applicable
shelf_life_ok  = days_remaining >= 3          # minimum viable shelf life
violation_3    = None if shelf_life_ok else f"SHELF_LIFE_CRITICAL: {days_remaining}d"

# Hard Constraint 4 — Allocation Bounds
allocation_ok  = qty_allocated + qty_proposed <= qty_ordered
violation_4    = None if allocation_ok else "ALLOCATION_EXCEEDS_ORDER"

# Collect all violations
hard_violations = [v for v in [violation_1, violation_2, violation_3, violation_4] if v]
```

---

### Step 7: Evaluate soft constraints and compute violation score

Soft constraints do not block the action but reduce its utility score:

```
soft_violation_score = 0.0

# Soft: capacity utilisation > 80% after action
if (on_hand + qty_proposed) / total_capacity_units > 0.8:
    soft_violation_score += 0.2

# Soft: quality is 'acceptable' (not ideal but not blocked)
if quality_status == 'acceptable':
    soft_violation_score += 0.1

# Soft: last_count_at > 30 days (stale physical count)
if staleness_days > 30:
    soft_violation_score += 0.1
```

---

### Step 8: Determine feasibility status

```
if len(hard_violations) > 0:
    feasibility_status = INFEASIBLE
    blocking_reason    = hard_violations[0]   # primary blocker

elif soft_violation_score > 0:
    feasibility_status = CONDITIONAL

else:
    feasibility_status = FEASIBLE
```

---

### Step 9: Return result

| Field | Value |
|---|---|
| `feasibility_status` | `FEASIBLE` / `CONDITIONAL` / `INFEASIBLE` |
| `violated_constraints` | List of hard constraint violation strings |
| `soft_violation_score` | Cumulative soft penalty [0–1] |
| `blocking_reason` | Primary hard constraint that blocks the action |
| `remaining_capacity` | Available units after proposed action |
| `quality_status` | Current stock quality label |

---

## Failure Modes

| Situation | Behaviour |
|---|---|
| Capacity endpoint unavailable | Assume `utilization_rate=0.9` (conservative), return `CONDITIONAL` |
| `quality_status` missing | Assume `acceptable`, add warning |
| Shelf-life data not available | Skip shelf-life check, add warning |
| `qty_ordered` missing | Skip allocation bound check, add warning |
| All hard constraints pass, soft score > 0.5 | Return `CONDITIONAL` with explicit list of soft violations |

---

## Example Walkthrough

**User query:** *"Can we ship 300 units of SKU-5501 from Location WH-A-07 to fill this customer order?"*

```
<thinking>
Before scoring this action's utility, I need to verify it satisfies all
hard constraints — quality, capacity, allocation bounds, shelf life.
</thinking>

Step 1 — search_knowledge_base("rational preferences constraints feasibility action space completeness")
→ Retrieved Ch.6 §6.1: rational agent operates only within feasible action space
→ Completeness + transitivity require all infeasible outcomes to be excluded first

Step 2 — get_entity_by_number(number="14.3")
→ Retrieved: robustness analysis — use conservative capacity baseline
→ Fallback: assume utilization=0.9 if capacity endpoint unavailable

Step 3 — GET /warehouses/WH-A/capacity-utilization
→ total_capacity=5000, used_capacity=3800
→ remaining_capacity = 1200 units

Step 4 — GET /observed-snapshot?product_id=SKU-5501&location_id=WH-A-07
→ on_hand=420, reserved=80, quality_status="good"
→ available = 420 − 80 = 340 units

Step 5 — GET /orders/ORD-8812
→ qty_ordered=300, qty_allocated=0, qty_shipped=0

Step 6 — Hard constraints:
    Capacity:   420 + 0 (outbound removes stock) → 420 ≤ 5000  ✓
    Quality:    "good" ∈ ('good', 'verified')                  ✓
    Shelf life: not applicable (non-perishable)                 ✓
    Allocation: 0 + 300 ≤ 300                                   ✓
    hard_violations = []

Step 7 — Soft constraints:
    Capacity after ship: (420−300)/5000 = 2.4% → well under 80%  ✓
    Quality = "good"                                              ✓
    last_count_at = 5 days ago                                   ✓
    soft_violation_score = 0.0

Step 8 — feasibility_status = FEASIBLE

Result:
  feasibility_status  = FEASIBLE
  violated_constraints = []
  soft_violation_score = 0.0
  remaining_capacity   = 1200 units after action
  quality_status       = good

All constraints satisfied. Action is cleared for utility scoring in SKILL-PU-01.
Available quantity (340 units) covers the requested 300 — proceed.
```

---

## Feeds Into

- `SKILL-DS-01` — `INFEASIBLE` actions are filtered out before ranking
- `SKILL-PU-01` — `soft_violation_score` can be subtracted from utility score
- `SKILL-MD-01` — `CONDITIONAL` status adds a confidence penalty