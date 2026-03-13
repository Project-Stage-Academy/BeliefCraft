---
name: decision-deferral-controller
description: "Decides whether to defer the current decision — waiting for better data — or commit now. Uses VOI and decision confidence to determine if exploration still pays off, then computes an optimal wait duration. Enforces hard limits: STOCKOUT_IMMINENT bypasses deferral entirely; maximum 2 deferrals and 48h wait are enforced to prevent indefinite delay. Questions like 'Should we wait for a cycle count before acting?', 'Is it safe to defer this order?', 'How long should we wait before deciding?'"
version: "1.0"
tags: [deferral, explore-then-commit, VOI, confidence, stopping-rule, meta-decision]
dependencies: [SKILL-PU-02, SKILL-MD-01, SKILL-RE-01, SKILL-DS-03]
---

# SKILL-MD-02 · Decision Deferral Controller

## When to Use This Skill

Activate this skill when the user asks about:
- Whether to act now or wait for more/better information
- How long the agent should delay before committing to a decision
- Whether the current confidence level justifies deferral
- As the final meta-decision gate after `SKILL-MD-01` returns `DEFER`
- Questions like *"Should we hold off on this order until we recount?"*
  or *"Is it worth waiting 24 hours for a fresh sensor reading?"*
  or *"We've already deferred once — should we defer again?"*

---

## Core Concept

Deferral is the warehouse analogue of **explore-then-commit**: spend k
steps gathering information, then commit to a greedy action (Ch.15 §15.3,
Algorithm 15.4, *Algorithms for Decision Making*).

```
# Explore-then-commit (Algorithm 15.4)
if k > 0:
    k -= 1
    return EXPLORE   # gather more info
else:
    return argmax_a ρ_a   # commit greedily
```

Warehouse translation: `k` = remaining deferral budget (max 2 deferrals,
48h total). While budget remains and VOI is positive, defer. Once budget
is exhausted, commit to the current best action regardless of confidence.

The deferral duration is calibrated using the **epsilon-decay schedule**
(Ch.15 §15.3, eq. 15.2): exploration decreases exponentially as evidence
accumulates. The optimal wait duration `τ` shrinks as the agent gains
confidence — more uncertainty → longer wait; near-confident → act soon.

```
ε ← α × ε     (eq. 15.2, α ∈ (0,1))
```

The optimal policy over the belief state (Ch.15 §15.5, eq. 15.5):

```
π*(w₁,ℓ₁,...,wₙ,ℓₙ) = argmax_a Q*(w₁,ℓ₁,...,wₙ,ℓₙ,a)    (eq. 15.5)
```

gives the formal basis: at each step the agent evaluates whether pulling
an information-gathering action (deferring) or a commitment action has
higher expected value. When `voi_net ≤ 0`, the commitment arm wins.

---

## Step-by-Step Execution

### Step 1: Retrieve explore-then-commit strategy from knowledge base

```
search_knowledge_base(
    query="explore then commit exploration phase k steps defer gather information commit greedy action",
    k=3
)
```

**What to extract from the result:**
- Ch.15 §15.3 — explore-then-commit (Algorithm 15.4):
  explore for first `k` steps, then commit to greedy action.
  Large `k` reduces risk of committing prematurely but wastes time.
- Warehouse mapping: `k` = remaining deferral count (starts at 2, decrements
  each time DEFER is returned). When `k = 0`, forced commit regardless of VOI.
- Key constraint: "large values for k reduce the risk of committing to a
  suboptimal action, but we waste more time exploring" — motivates hard cap.

---

### Step 2: Retrieve epsilon-decay and optimal exploration policy equations

```
get_entity_by_number(number="15.2")
```

**What to extract from the result:**
- Ch.15 §15.3, eq. 15.2 — epsilon-decay: `ε ← α × ε`, α ∈ (0,1)
- Use this to compute optimal wait duration: as uncertainty decreases
  (more evidence gathered), the wait window should shrink proportionally.
- Warehouse mapping: `τ_optimal = uncertainty_index × τ_max`
  where `τ_max = 48h` is the hard cap. High uncertainty → long wait;
  near-certain → short wait before the next observation cycle.

```
get_entity_by_number(number="15.5")
```

**What to extract from the result:**
- Ch.15 §15.5, eq. 15.5 — optimal bandit policy:
  `π*(beliefs) = argmax_a Q*(beliefs, a)` — at each belief state, the
  agent commits when the commit arm has higher expected value than the
  explore arm. This is exactly the VOI test: `voi_net > 0` → explore arm
  wins; `voi_net ≤ 0` → commit arm wins.

---

### Step 3: Check hard bypass conditions

Before any VOI or confidence calculation, evaluate absolute overrides:

```
# Bypass 1 — STOCKOUT_IMMINENT: never defer when inventory is critical
if trigger_event == STOCKOUT_IMMINENT:   # from SKILL-DS-03
    return {
        deferral_decision: CANNOT_DEFER,
        bypass_reason:     STOCKOUT_IMMINENT,
        recommended_next_step: EXECUTE_IMMEDIATELY
    }

# Bypass 2 — deferral budget exhausted
if deferral_count >= MAX_DEFERRAL_COUNT:   # MAX_DEFERRAL_COUNT = 2
    return {
        deferral_decision: FORCED_DECISION,
        bypass_reason:     MAX_DEFERRALS_REACHED,
        recommended_next_step: EXECUTE_WITH_FLAG
    }
```

---

### Step 4: Evaluate VOI and confidence gate

Requires from upstream skills:
- `voi_net` from `SKILL-PU-02`
- `confidence_class` from `SKILL-MD-01`
- `uncertainty_index` from `SKILL-RE-01`

```
# Two conditions must BOTH hold to justify deferral
# (explore arm beats commit arm in eq. 15.5)
voi_justifies_wait    = voi_net > 0
confidence_low_enough = confidence_class in [LOW_CONFIDENCE, INSUFFICIENT]

should_defer = voi_justifies_wait AND confidence_low_enough
```

If `voi_net ≤ 0`: information gain does not cover the cost of delay.
If `confidence_class` is CONFIDENT or ADEQUATE: already good enough to act.
Either condition alone is sufficient to reject deferral.

---

### Step 5: Compute optimal wait duration

Using the epsilon-decay mapping from Step 2 (eq. 15.2):

```
# τ_optimal scales linearly with uncertainty_index
# (analogous to ε decaying as confidence grows)
MAX_DEFERRAL_HOURS = 48     # hard cap
τ_optimal = uncertainty_index × MAX_DEFERRAL_HOURS

# Round to nearest observation cycle (default: 6h)
OBSERVATION_CYCLE_HOURS = 6
τ_optimal = ceil(τ_optimal / OBSERVATION_CYCLE_HOURS) × OBSERVATION_CYCLE_HOURS
τ_optimal = min(τ_optimal, MAX_DEFERRAL_HOURS)
```

---

### Step 6: Fetch last observation timestamp for staleness check

```
GET /api/v1/smart-query/inventory/observed-snapshot
    ?product_id=<product_id>
    &location_id=<location_id>
```

**Fields to extract:** `last_count_at` (or `observed_at`)

```
hours_since_last_obs = (now - last_count_at).total_hours

# If a fresh observation is already imminent, reduce wait accordingly
if hours_since_last_obs < OBSERVATION_CYCLE_HOURS:
    τ_optimal = OBSERVATION_CYCLE_HOURS - hours_since_last_obs
```

---

### Step 7: Increment deferral counter and return result

```
if should_defer:
    deferral_count_new = deferral_count + 1
    deferral_decision  = DEFER
else:
    deferral_count_new = deferral_count   # unchanged — not deferring
    deferral_decision  = CANNOT_DEFER
```

---

### Step 8: Return result

| Field | Value |
|---|---|
| `deferral_decision` | `DEFER` / `CANNOT_DEFER` / `FORCED_DECISION` |
| `bypass_reason` | `STOCKOUT_IMMINENT` / `MAX_DEFERRALS_REACHED` / `null` |
| `optimal_wait_hours` | Recommended wait duration (hours) if `DEFER` |
| `deferral_count` | Updated deferral counter after this call |
| `deferrals_remaining` | `MAX_DEFERRAL_COUNT − deferral_count` |
| `hours_since_last_obs` | Staleness of latest inventory observation |
| `voi_net_used` | `voi_net` value that drove the decision |
| `confidence_class_used` | `confidence_class` from SKILL-MD-01 |
| `recommended_next_step` | `WAIT_AND_REOBSERVE` / `EXECUTE` / `EXECUTE_WITH_FLAG` |

---

## Failure Modes

| Situation | Behaviour |
|---|---|
| `SKILL-PU-02` not run | Treat `voi_net = 0`; skip VOI gate → CANNOT_DEFER unless confidence forces deferral |
| `SKILL-MD-01` not run | Treat `confidence_class = ADEQUATE`; skip confidence gate → CANNOT_DEFER |
| `trigger_event` unavailable | Skip bypass check; proceed with VOI+confidence gate only |
| `last_count_at` unavailable | Use `hours_since_last_obs = 24h` (conservative); τ_optimal unchanged |
| `uncertainty_index = 0` | `τ_optimal = 0h`; deferral not meaningful → CANNOT_DEFER |
| `voi_net > 0` but `confidence_class = CONFIDENT` | CANNOT_DEFER — agent is already confident enough; VOI alone does not justify delay |

---

## Example Walkthrough

**User query:** *"We're not confident about the SKU-1102 reorder decision — should we defer and count stock first, or commit now?"*

```
<thinking>
I need to determine whether deferral is justified by checking:
1. Hard bypass conditions (STOCKOUT_IMMINENT, max deferrals)
2. VOI gate (does information gathering pay off?)
3. Confidence gate (are we too uncertain to act?)
Then compute optimal wait duration if deferring.
</thinking>

Step 1 — search_knowledge_base("explore then commit exploration phase k steps defer gather information commit greedy action")
→ Retrieved: Ch.15 §15.3 Algorithm 15.4 — explore-then-commit:
  "explore for first k steps, then return argmax_a ρ_a"
  "large k reduces risk of suboptimal commit, but wastes time" → cap at k=2

Step 2 — get_entity_by_number(number="15.2")
→ Retrieved: ε ← α × ε  (eq. 15.2) — epsilon decays as evidence grows
  τ_optimal = uncertainty_index × MAX_DEFERRAL_HOURS

        get_entity_by_number(number="15.5")
→ Retrieved: π*(beliefs) = argmax_a Q*(beliefs, a)  (eq. 15.5)
  Deferral justified iff explore arm (gather info) beats commit arm:
  → equivalent to voi_net > 0 AND confidence is LOW

Step 3 — Bypass checks:
    trigger_event  = REORDER_TRIGGER  (from SKILL-DS-03, not STOCKOUT_IMMINENT)
    deferral_count = 1  (already deferred once)
    MAX_DEFERRAL_COUNT = 2
    → Neither bypass fires; 1 deferral remaining

Step 4 — VOI and confidence gate:
    voi_net          = 0.03   (from SKILL-PU-02)  → voi_justifies_wait = True
    confidence_class = LOW_CONFIDENCE  (from SKILL-MD-01, C=0.38)
    → confidence_low_enough = True
    → should_defer = True ✓

Step 5 — Optimal wait duration:
    uncertainty_index   = 0.61  (from SKILL-RE-01)
    τ_optimal           = 0.61 × 48 = 29.3h
    → rounded to 6h cycle: ceil(29.3/6) × 6 = 30h

Step 6 — GET /observed-snapshot → last_count_at = 19h ago
    hours_since_last_obs = 19h
    Next cycle due in: 6 − (19 mod 6) = 5h
    → τ_optimal adjusted to max(30h, 6h) = 30h  (already beyond one cycle)

Step 7 — Increment deferral:
    deferral_count_new = 2
    deferrals_remaining = 0  ← after this deferral, budget exhausted

Result:
  deferral_decision    = DEFER
  optimal_wait_hours   = 30
  deferral_count       = 2
  deferrals_remaining  = 0
  hours_since_last_obs = 19h
  recommended_next_step = WAIT_AND_REOBSERVE

Deferral is justified: VOI is positive (0.03) and confidence is LOW.
Wait 30 hours for the next observation cycle, then re-run the full
decision pipeline. Warning: this is the final permitted deferral
(budget = 2/2 exhausted). On the next call, FORCED_DECISION will
be returned and the agent must commit regardless of confidence.
```

---

## Feeds Into

- **Executor / orchestrator** — `deferral_decision` is the terminal output;
  `DEFER` suspends execution for `optimal_wait_hours`, then restarts pipeline
- `SKILL-DS-03` — after the wait, re-run DS-03 to check if `trigger_event`
  has escalated to STOCKOUT_IMMINENT (would bypass deferral on next call)
- `SKILL-MD-01` — after the wait, re-run MD-01; rising confidence should
  eventually return ADEQUATE or CONFIDENT, allowing EXECUTE
- `SKILL-PU-02` — after the wait, re-run PU-02; if new observation was
  gathered, `voi_net` should drop to ≤ 0, unlocking commitment