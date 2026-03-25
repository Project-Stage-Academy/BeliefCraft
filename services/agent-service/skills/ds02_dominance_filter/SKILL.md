---
name: stochastic-dominance-filter
description: "Filters a set of candidate actions down to the Pareto frontier by removing actions that are dominated — worse than some alternative on every utility attribute simultaneously. Returns only non-dominated actions to reduce the decision set before final ranking. Use between `multi-attribute-utility-scorer` (scoring) and `expected-utility-action-ranker` (ranking) when there are 4+ candidates. Questions like 'Which options can we rule out entirely?', 'Are there any strictly inferior choices here?', 'Trim the candidate list before we decide.'"
version: "1.0"
tags: [dominance, pareto, pruning, filtering, multi-attribute, decision]
dependencies:
  - multi-attribute-utility-scorer
---

# Stochastic Dominance Filter

## When to Use This Skill

Activate this skill when the user asks about:
- Eliminating clearly inferior options before final ranking
- Which actions can be ruled out without loss of optimality
- Reducing a large candidate set (≥ 4 actions) to a tractable frontier
- As an intermediate filter between `multi-attribute-utility-scorer` (scoring) and `expected-utility-action-ranker` (ranking)
- Questions like *"We have six replenishment options — which can we drop immediately?"*
  or *"Are any of these supplier choices strictly worse than the others?"*

---

## Core Concept

An action **A dominates action B** if A is at least as good as B on every
utility attribute, and strictly better on at least one. A dominated action
can never be the optimal choice, regardless of how the weights are set.

This is grounded in two places in *Algorithms for Decision Making*:

**1. Pareto optimality (Ch.14 §14.4 Trade Analysis):**
> "A policy is called Pareto optimal if it is not dominated by any other
> policy in that space. The set of Pareto optimal policies is called the
> Pareto frontier."

Policies (actions) that are dominated can be *eliminated from consideration*
before any further analysis — this is the formal justification for filtering.

**2. Alpha-vector pruning (Ch.20 §20.4, eq. 20.16):**
An alpha vector α is dominated by a set Γ if the maximum utility gap δ
achievable over all beliefs is negative:

```
maximize  δ, b
subject to  b ≥ 0,   1ᵀb = 1
            αᵀb ≥ α'ᵀb + δ   for all α' ∈ Γ     (eq. 20.16)

α is dominated  ⟺  max δ < 0
α is NOT dominated  ⟺  max δ > 0
```

For the warehouse agent, each action has a `utility_breakdown`
vector `[u_fill, u_penalty, u_lt, u_sla]` which plays the role of α.
The dominance check is componentwise — no LP required.

---

## Step-by-Step Execution

### Step 1: Retrieve Pareto optimality definition from knowledge base

```
search_knowledge_base(
    query="Pareto optimal frontier dominated policy eliminate trade-off multiple objectives",
    k=3
)
```

**What to extract from the result:**
- Ch.14 §14.4 — Pareto frontier definition: a policy is Pareto optimal if
  no other policy is at least as good on all metrics and strictly better on
  at least one. Dominated policies can be eliminated from consideration.
- Practical implication: run this filter before utility-weighted ranking to
  reduce the candidate set without risk of discarding the optimal action.

---

### Step 2: Retrieve alpha-vector dominance criterion

```
get_entity_by_number(number="20.16")
```

**What to extract from the result:**
- Ch.20 §20.4 eq. 20.16 — α is dominated by Γ iff the maximum utility gap
  δ over all beliefs is negative: `max δ = α'ᵀb − αᵀb > 0` for some α' ∈ Γ.
- Warehouse translation: action A dominates action B when
  `u_A[k] ≥ u_B[k]` for all attributes k, and `u_A[k] > u_B[k]` for at
  least one k. Equivalent to δ < 0 for B relative to the set containing A.

---

### Step 3: Retrieve utility breakdowns from `multi-attribute-utility-scorer`

Requires for each candidate action:
- `utility_breakdown`: `{u_fill, u_penalty, u_lt, u_sla}` — all four
  attribute-level utility scores (not just the weighted scalar)
- `action_id`: identifier for the action
- `feasibility_status` from `constraint-satisfaction-validator` (if available)

**Pre-filter:** remove any action with `feasibility_status = INFEASIBLE`
before running dominance checks. Infeasible actions are already eliminated;
do not let them "dominate" a feasible CONDITIONAL action.

```
candidates = [a for a in actions
              if feasibility_status(a) != INFEASIBLE]
```

---

### Step 4: Compute pairwise dominance

Using the componentwise criterion from Step 2:

```
ATTRS = ['u_fill', 'u_penalty', 'u_lt', 'u_sla']

def dominates(a, b, utility_breakdown):
    """
    Returns True if action a dominates action b.
    Dominance: a ≥ b on ALL attributes AND a > b on AT LEAST ONE.
    Corresponds to δ < 0 for b in eq. 20.16 relative to set {a}.
    """
    all_geq = all(
        utility_breakdown[a][k] >= utility_breakdown[b][k]
        for k in ATTRS
    )
    any_gt = any(
        utility_breakdown[a][k] > utility_breakdown[b][k]
        for k in ATTRS
    )
    return all_geq and any_gt

# Build dominance relation matrix
dominated = set()
for a in candidates:
    for b in candidates:
        if a != b and dominates(a, b, utility_breakdown):
            dominated.add(b)

# Pareto frontier = candidates not dominated by anyone
pareto_frontier = [a for a in candidates if a not in dominated]
dominated_actions = list(dominated)
```

---

### Step 5: Handle near-dominance (soft dominance)

Pure componentwise dominance can miss cases where one action is nearly
dominated — slightly better on one attribute but substantially worse on
all others. Flag these as `near_dominated` for transparency:

```
NEAR_DOMINANCE_THRESHOLD = 0.05   # within 0.05 on all attrs

def near_dominates(a, b, utility_breakdown):
    """
    Returns True if a near-dominates b:
    a ≥ b − threshold on ALL attributes AND
    a strictly exceeds b on the weighted scalar.
    """
    near_geq = all(
        utility_breakdown[a][k] >= utility_breakdown[b][k] - NEAR_DOMINANCE_THRESHOLD
        for k in ATTRS
    )
    scalar_better = action_utility_score[a] > action_utility_score[b]
    return near_geq and scalar_better

near_dominated = [
    b for b in pareto_frontier
    if any(near_dominates(a, b, utility_breakdown)
           for a in pareto_frontier if a != b)
]
```

---

### Step 6: Return result

| Field | Value |
|---|---|
| `pareto_frontier` | List of action IDs not dominated by any other candidate |
| `dominated_actions` | List of action IDs that were eliminated |
| `near_dominated` | Frontier members flagged as near-dominated (advisory) |
| `frontier_size` | `len(pareto_frontier)` |
| `input_count` | Number of candidates before filtering |
| `reduction_ratio` | `1 − frontier_size / input_count` — fraction eliminated |

---

## Failure Modes

| Situation | Behaviour |
|---|---|
| Only one candidate | Return it as the frontier, `dominated_actions=[]`, `reduction_ratio=0` |
| No candidate dominates any other (all on frontier) | Return full set, `dominated_actions=[]`, warn that DS-01 must break the tie |
| `utility_breakdown` missing for some actions | Skip those actions from dominance check, add `data_gap_flag=True` |
| All candidates have identical breakdowns | Return all as frontier (no dominance), flag `all_tied=True` |
| `constraint-satisfaction-validator` not run (no feasibility info) | Run dominance on all candidates, add warning that infeasible actions may be present |

---

## Example Walkthrough

**User query:** *"We have five supplier options for SKU-5502 — can you trim out the ones we definitely shouldn't consider?"*

```
<thinking>
I need to find which actions are dominated across all four utility
dimensions. Any action that is weakly worse than another on every
attribute can be eliminated without loss of optimality.
</thinking>

Step 1 — search_knowledge_base("Pareto optimal frontier dominated policy eliminate trade-off multiple objectives")
→ Retrieved: Ch.14 §14.4 — Pareto frontier definition:
  "policies that are dominated by others can be eliminated from consideration"
→ Confirmed: dominance filter is lossless — optimal action always survives

Step 2 — get_entity_by_number(number="20.16")
→ Retrieved: eq. 20.16 — α dominated by Γ iff max δ < 0
→ Warehouse translation: A dominates B iff u_A[k] ≥ u_B[k] ∀k AND ∃k: u_A[k] > u_B[k]

Step 3 — Upstream utility_breakdown from `multi-attribute-utility-scorer`:

    Action A: {u_fill=0.92, u_penalty=0.55, u_lt=1.00, u_sla=1.00}  feasibility=FEASIBLE
    Action B: {u_fill=0.70, u_penalty=0.40, u_lt=0.60, u_sla=0.75}  feasibility=FEASIBLE
    Action C: {u_fill=0.88, u_penalty=0.60, u_lt=0.60, u_sla=0.50}  feasibility=FEASIBLE
    Action D: {u_fill=0.65, u_penalty=0.35, u_lt=0.60, u_sla=0.75}  feasibility=INFEASIBLE
    Action E: {u_fill=0.95, u_penalty=0.50, u_lt=0.60, u_sla=0.75}  feasibility=FEASIBLE

    Pre-filter: remove D (INFEASIBLE) → candidates = [A, B, C, E]

Step 4 — Pairwise dominance checks:

    Does A dominate B?
      u_fill:   0.92 ≥ 0.70  ✓
      u_penalty: 0.55 ≥ 0.40  ✓
      u_lt:     1.00 ≥ 0.60  ✓
      u_sla:    1.00 ≥ 0.75  ✓
      Any strictly greater? Yes (all four)  ✓
      → A DOMINATES B  ✗ B is eliminated

    Does A dominate C?
      u_fill:   0.92 ≥ 0.88  ✓
      u_penalty: 0.55 ≥ 0.60?  ✗  (0.55 < 0.60)
      → A does NOT dominate C

    Does A dominate E?
      u_fill:   0.92 ≥ 0.95?  ✗
      → A does NOT dominate E

    Does E dominate C?
      u_fill:   0.95 ≥ 0.88  ✓
      u_penalty: 0.50 ≥ 0.60?  ✗
      → E does NOT dominate C

    Does C dominate E?
      u_fill:   0.88 ≥ 0.95?  ✗
      → C does NOT dominate E

    No further domination pairs found.

Step 5 — Near-dominance check on frontier [A, C, E]:
    A vs C: A near-dominates C?
      u_fill:   0.92 ≥ 0.88−0.05=0.83  ✓
      u_penalty: 0.55 ≥ 0.60−0.05=0.55  ✓ (exactly at threshold)
      u_lt:     1.00 ≥ 0.60−0.05=0.55  ✓
      u_sla:    1.00 ≥ 0.50−0.05=0.45  ✓
      Scalar: A(0.847) > C(0.716)  ✓
      → C is NEAR_DOMINATED by A (advisory flag)

Step 6 — Result:
    pareto_frontier   = [A, C, E]
    dominated_actions = [B]
    near_dominated    = [C]
    frontier_size     = 3
    input_count       = 4  (after INFEASIBLE pre-filter)
    reduction_ratio   = 0.25  (1 strictly eliminated)

Action B is eliminated — strictly dominated by A on all four dimensions.
Action D was already infeasible.
Remaining frontier: A, C, E — pass these to `expected-utility-action-ranker` for final ranking.
Note: C is near-dominated by A (advisory). If the penalty attribute weight
is increased, C would be eliminated entirely.
```

---

## Feeds Into

- `expected-utility-action-ranker` — receives `pareto_frontier` as its candidate set instead of
  the full unfiltered list; `dominated_actions` are excluded from ranking
- `decision-confidence-estimator` — `frontier_size` feeds into decision confidence:
  a frontier of 1 → HIGH confidence; frontier of 4+ → lower margin signal
- `value-of-information` — if `frontier_size > 2` and scores are close, VOI
  recalculation may be warranted before committing to the top action
