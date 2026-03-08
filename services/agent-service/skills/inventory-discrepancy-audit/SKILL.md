---
name: inventory-discrepancy-audit
description: Diagnostic workflow for investigating inventory shrinkage, counting errors, and sensor data quality issues in warehouse operations
version: "1.0"
tags: [inventory, audit, discrepancy, shrinkage, quality-control]
dependencies: []
---

# Inventory Discrepancy Audit

## When to Use This Skill

Activate this skill when the user asks about:
- Inventory shrinkage or unexplained losses
- Discrepancies between expected and observed inventory
- Counting accuracy issues or stock mismatches
- Sensor reliability affecting inventory data quality
- Questions like "Why is my inventory count wrong?" or "How can I trace inventory discrepancies?"

## Core Diagnostic Framework

Inventory discrepancies stem from one of **three root causes**:

1. **Sensor/Observation Errors** - Hardware malfunction, calibration drift, signal noise
2. **Process Failures** - Incorrect picks, mislabeled stock, unreported movements
3. **External Factors** - Theft, damage, expired goods not recorded

## Step-by-Step Investigation Protocol

### Step 1: Identify Affected Products
Use observation tools to isolate problematic SKUs:
```
Tools: get_observed_inventory_snapshot
Parameters: {quality_threshold: 0.7, include_anomalies: true}
```

**Decision Point**: If multiple products show discrepancies, prioritize by value (ABC analysis).

### Step 2: Validate Sensor Health
Check devices contributing to inventory observations:
```
Tools: list_sensor_devices, get_device_health_summary
Focus: anomaly_count, last_calibration, signal_quality
```

**Known Patterns**:
- `anomaly_count > 5` in 24 hours → Likely hardware issue
- `signal_quality < 0.8` → Check calibration or positioning
- No recent calibration → Schedule maintenance

### Step 3: Trace Inventory Movements
Audit recent transactions for the affected product:
```
Tools: list_inventory_moves, get_inventory_move_audit_trace
Parameters: {product_id: "<SKU>", start_date: "<T-7days>"}
```

**Red Flags**:
- Moves without corresponding receipts/shipments
- Adjustments without approval codes
- Unusual transfer patterns (e.g., high-value items to low-security zones)

### Step 4: Cross-Reference Procurement Data
Verify expected quantities against purchase orders:
```
Tools: list_purchase_orders, get_purchase_order
Filter: status="received", product_id="<SKU>"
```

**Check**: `received_quantity` vs. `ordered_quantity` — partial deliveries can cause count mismatches.

### Step 5: Calculate Discrepancy Severity
Apply statistical reasoning to quantify the issue:

**Shrinkage Rate Formula**:
```
shrinkage_rate = (expected_qty - observed_qty) / expected_qty * 100
```

**Confidence Interval** (95%):
```python
import numpy as np
from scipy.stats import norm

expected = 1000
observed = 950
std_dev = 15  # historical variance

z_score = (expected - observed) / std_dev
p_value = norm.sf(abs(z_score)) * 2

if p_value < 0.05:
    conclusion = "Statistically significant discrepancy — investigate further"
else:
    conclusion = "Within normal operational variance"
```

### Step 6: Formulate Corrective Actions

Based on root cause:

| Root Cause | Recommended Action |
|-----------|-------------------|
| Sensor drift | Recalibrate devices, verify placement |
| Process error | Review picking procedures, audit staff training |
| Theft/damage | Increase security, cycle count frequency |
| Data lag | Check sync intervals, investigate delayed updates |

## Decision-Making Algorithm Reference

This skill applies **Partially Observable Markov Decision Process (POMDP)** principles:

- **Belief State**: Our confidence in the true inventory level given noisy observations
- **Observation Model**: Sensor accuracy distribution (Gaussian noise assumption)
- **Transition Model**: Inventory flow based on moves, receipts, issues

**Key Insight**: Never trust a single observation. Always aggregate multiple sensors and cross-check with transactional records.

## Example Walkthrough

**User Query**: "Why do I have 50 fewer units of product P123 than expected?"

**Agent Response**:
```
<thinking>
User reports inventory discrepancy for P123. Need to:
1. Check sensor health for P123 location
2. Audit recent moves for P123
3. Verify procurement receipts
4. Calculate if shrinkage is within normal variance
</thinking>

I'll investigate the discrepancy for product P123. Let me start by checking sensor health...

[Calls: get_device_health_summary for P123 location]
[Calls: list_inventory_moves for P123, last 7 days]
[Calls: get_purchase_order for recent P123 receipts]

Analysis:
- Sensor anomaly_count: 0 (devices healthy)
- 3 outbound moves totaling 45 units (documented)
- 1 adjustment: -5 units (code: "damage-write-off")
- Procurement: All receipts match ordered quantities

Conclusion:
The 50-unit discrepancy is explained by:
- 45 units: Legitimate shipments to customers
- 5 units: Damaged goods write-off

**No anomaly detected**. Discrepancy is fully accounted for by documented transactions.

Recommendation: Review damage patterns if write-offs exceed 2% monthly.
```

## Supporting Files

(None currently — future: add `SENSOR_CALIBRATION_CHECKLIST.md`, `ABC_ANALYSIS_GUIDE.md`)

## Metadata

- **Complexity**: Intermediate (requires multi-tool orchestration)
- **Average Execution Time**: 4-6 tool calls, ~30 seconds
- **Success Criteria**: Root cause identified with >80% confidence
