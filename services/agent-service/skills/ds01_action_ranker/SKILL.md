---
name: expected-utility-action-ranker
description: "Ranks candidate actions by expected utility and selects the best admissible action, accounting for uncertainty via confidence intervals. Filters out INFEASIBLE actions before ranking. Returns a ranked list with decision confidence (HIGH / MARGINAL / TIE). Use as the final selection step after scoring and constraint validation. Questions like 'Which action should we take?', 'What is the best replenishment option?', 'Rank these supplier choices.'"
version: "1.0"
tags: [action-ranking, MEU, decision, greedy, confidence, beam-search]
dependencies:
  - multi-attribute-utility-scorer
  - constraint-satisfaction-validator
  - inventory-uncertainty-quantifier
---

# Expected-Utility Action Ranker

## When to Use This Skill

Activate this skill when the user asks about:
- Which of several candidate actions to execute
- Final selection after scoring and constraint filtering
- How confident the agent is in its top recommendation
- Questions like *"Which replenishment option should we go with?"*
  or *"Rank these three supplier orders by expected utility."*

---

## Core Concept

A rational agent selects the action that maximises expected utility
(Ch.6 §6.4, eq. 6.8, *Algorithms for Decision Making*):

```
a* = argmax_a EU(a | o)     (eq. 6.8)
```

This is equivalent to the **greedy policy** with respect to the utility
function (Ch.7 §7.3, eq. 7.14):

```
π(s) = argmax_a Q(s, a)     (eq. 7.14)
```

Under uncertainty (`posterior_std > 0` from `inventory-uncertainty-quantifier`), the utility
score has a confidence interval. If two actions' CIs overlap, the decision
is MARGINAL or TIE and should be flagged for human review or escalated to
`decision-confidence-estimator`.

The **advantage function** (Ch.7 §7.3, eq. 7.15) provides the decision margin:

```
A(s, a) = Q(s, a) − U(s)   →   margin = score[0] − score[1]
```

A wide margin → HIGH confidence. A narrow margin → escalate.

---

## Step-by-Step Execution

### Step 1: Retrieve MEU and greedy policy from knowledge base

```
search_knowledge_base(
    query="maximum expected utility argmax action greedy policy value function ranking selection",
    k=3
)
```

**What to extract from the result:**
- MEU principle (Ch.6 §6.4, eq. 6.8): `a* = argmax_a EU(a | o)`
- Greedy policy (Ch.7 §7.3, eq. 7.14): `π(s) = argmax_a Q(s, a)`
- Advantage function (eq. 7.15): `A(s, a) = Q(s, a) − U(s)`
  — use as decision margin: margin = score[0] − score[1]

---

### Step 2: Retrieve confidence interval / quantile exploration framing

```
get_entity_by_number(number="7.14")
```

**What to extract from the result:**
- Greedy action selection as `argmax_a Q(s, a)` — the basis for ranking
- When scores are close, use uncertainty bounds before committing

```
search_knowledge_base(
    query="upper confidence bound uncertainty action score interval quantile exploration optimism",
    k=2
)
```

**What to extract from the result:**
- Ch.15 §15.4 — upper confidence bound exploration: choose the action with
  the highest α-quantile score when scores are uncertain
- Apply: `CI = score ± 1.96 × uncertainty_index × 0.1` to each candidate

---

### Step 3: Collect scored and validated candidates

Requires from upstream skills for each candidate action:
- `action_utility_score` from `multi-attribute-utility-scorer`
- `feasibility_status` from `constraint-satisfaction-validator`
- `uncertainty_index` from `inventory-uncertainty-quantifier`

**Filter step — eliminate inadmissible actions:**
```
candidates = [a for a in actions if feasibility_status(a) ≠ INFEASIBLE]
```

If no candidates remain after filtering → return `data_gap_flag=True`,
escalate immediately.

---

### Step 4: Compute confidence intervals and rank

Using the advantage function framing from Step 1:

```
for each candidate a:
    score(a)    = action_utility_score from multi-attribute-utility-scorer
    ci_lower(a) = score(a) − 1.96 × uncertainty_index × 0.1
    ci_upper(a) = score(a) + 1.96 × uncertainty_index × 0.1

# Sort descending by score
ranked = sort(candidates, by=score, descending=True)

# Beam filter — keep top beam_width=3 candidates
beam = ranked[:3]

# Compute advantage margin (eq. 7.15)
margin = score(beam[0]) − score(beam[1])   if len(beam) ≥ 2 else 1.0
```

---

### Step 5: Classify decision confidence

```
if margin > 0.10:
    decision_confidence = HIGH
elif margin > 0.02:
    decision_confidence = MARGINAL
else:
    decision_confidence = TIE    # escalate to signal-conflict-resolver

# Tie-break when margin ≤ 0.02:
#   1st: highest sla_priority
#   2nd: highest posterior_mean_reliability (from supplier-reliability-aggregator)
```

---

### Step 6: Return result

| Field | Value |
|---|---|
| `ranked_actions` | Ordered list of admissible candidates with scores and CIs |
| `top_action_id` | ID of the recommended action |
| `top_action_score` | Utility score of the top action |
| `margin` | Score difference between #1 and #2 (advantage, eq. 7.15) |
| `decision_confidence` | `HIGH` / `MARGINAL` / `TIE` |
| `beam_width_used` | Number of candidates retained in beam |
| `filtered_count` | Number of INFEASIBLE actions removed |

---

## Failure Modes

| Situation | Behaviour |
|---|---|
| All candidates INFEASIBLE | Return empty ranking, `data_gap_flag=True`, escalate |
| Only one candidate | `margin=1.0`, `decision_confidence=HIGH` by default |
| `multi-attribute-utility-scorer` not run | Cannot rank — require upstream scoring first |
| `uncertainty_index` unavailable | Use `CI = score ± 0.05` as conservative default |
| All scores identical | `TIE`, apply tie-break rules, flag for human review |

---

## Example Walkthrough

**User query:** *"We have four replenishment options for SKU-7701 — which one should we go with?"*

```
<thinking>
I have utility scores and feasibility results for four actions.
I need to filter infeasible ones, rank by EU, compute the margin,
and classify decision confidence.
</thinking>

Step 1 — search_knowledge_base("maximum expected utility argmax action greedy policy value function ranking")
→ Retrieved: a* = argmax_a EU(a|o)  (eq. 6.8)
→ Retrieved: π(s) = argmax_a Q(s,a)  (eq. 7.14)
→ Retrieved: margin = A(s,a) = Q(s,a) − U(s)  (eq. 7.15)

Step 2 — get_entity_by_number(number="7.14")
→ Confirmed: greedy action selection = argmax Q

        search_knowledge_base("upper confidence bound uncertainty action score interval")
→ Retrieved: CI = score ± α-quantile × uncertainty  (Ch.15 §15.4)

Step 3 — Upstream results:
    Action A: score=0.81, feasibility=FEASIBLE,    uncertainty=0.22
    Action B: score=0.74, feasibility=FEASIBLE,    uncertainty=0.31
    Action C: score=0.67, feasibility=INFEASIBLE,  reason=CAPACITY_EXCEEDED
    Action D: score=0.79, feasibility=CONDITIONAL, uncertainty=0.18

    After filter (remove INFEASIBLE): candidates = [A, B, D]
    filtered_count = 1

Step 4 — Compute CIs and rank:
    Action A: CI = [0.81 ± 1.96×0.022] = [0.767, 0.853]
    Action D: CI = [0.79 ± 1.96×0.018] = [0.755, 0.825]
    Action B: CI = [0.74 ± 1.96×0.031] = [0.679, 0.801]

    ranked = [A(0.81), D(0.79), B(0.74)]
    beam   = [A, D, B]
    margin = 0.81 − 0.79 = 0.02

Step 5 — Classify confidence:
    margin = 0.02  →  TIE threshold
    Tie-break: A has sla_priority=1, D has sla_priority=2
    → top_action = A, decision_confidence = MARGINAL

Result:
  top_action_id      = Action A
  top_action_score   = 0.81
  margin             = 0.02
  decision_confidence = MARGINAL

Action A is recommended but the margin is very narrow (0.02).
Action D is nearly equivalent — consider escalating to `decision-confidence-estimator`
to assess whether decision confidence is sufficient to execute,
or to `signal-conflict-resolver` if signal conflict may explain the tie.
```

---

## Feeds Into

- `decision-confidence-estimator` — uses `decision_confidence` and `margin` for overall confidence score
- `signal-conflict-resolver` — called when `decision_confidence = TIE` to resolve conflicts
- `decision-deferral-controller` — called when `decision_confidence = MARGINAL` to evaluate deferral
- `value-of-information` — if `TIE`, recomputes VOI to check if more info would break the tie
