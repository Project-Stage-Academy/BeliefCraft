Integration Specification: Environment API for BeliefCraft Agent
Overview
This document outlines the required API endpoints and data structures needed for the BeliefCraft ReAct agent to monitor and analyze warehouse states. The agent interacts with these endpoints via the EnvironmentAPIClient.

Base Configuration
Communication Format: JSON

Base URL: ENVIRONMENT_API_URL (as defined in environment settings)

Required Endpoints
1. Current Warehouse Observations
Endpoint: GET /observations/current

Description: Retrieves real-time sensor data and inventory levels.

Query Parameters:

product_id (string, optional): Filter by product UUID.

location_id (string, optional): Filter by specific location UUID.

warehouse_id (string, optional): Filter by warehouse UUID.

Agent-side Caching: Disabled (skip_cache: True). This data must always be fresh.

2. Order Backlog
Endpoint: GET /orders/backlog

Description: Retrieves unfulfilled orders with deadlines and priorities.

Query Parameters:

status (string, optional): Enum [pending, processing, at_risk].

priority (string, optional): Enum [low, medium, high, critical].

Agent-side Caching: Disabled (skip_cache: True).

3. Inventory History
Endpoint: GET /inventory/history/{product_id}

Description: Historical inventory movements for trend analysis.

Path Parameters:

product_id (string, required): Product UUID.

Query Parameters:

days (integer, default: 30): History depth (max: 365).

Agent-side Caching: 1 hour (TTL: 3600s).

4. Shipments in Transit
Endpoint: GET /shipments/in-transit

Description: Tracks inbound, outbound, and inter-warehouse shipments.

Query Parameters:

warehouse_id (string, optional): Filter by destination warehouse.

Agent-side Caching: 5 minutes (TTL: 300s).

5. Stockout Probability Analysis
Endpoint: GET /analysis/stockout-probability/{product_id}

Description: Calculates the likelihood of a stockout.

Path Parameters:

product_id (string, required).

Agent-side Caching: 10 minutes (TTL: 600s).

6. Lead Time Risk Assessment
Endpoint: GET /analysis/lead-time-risk

Description: Analyzes historical lead time variance and reliability (CVaR).

Query Parameters:

supplier_id (string, optional).

route_id (string, optional).

Agent-side Caching: 10 minutes (TTL: 600s).

Technical Expectations for the Environment Team
Error Handling: Please return standard HTTP status codes. For 4xx and 5xx errors, include a JSON body: {"detail": "error_message_here"}.

Schema Consistency: Ensure that parameter names in the API match the query parameters listed above to avoid mapping issues in the APIClientTool.

Performance: Since the agent may call multiple tools in a single "Think-Act" loop, endpoint latency should ideally be under 500ms.

Parameter Validation Requirements
The agent-side tools expect the Environment API to validate and reject invalid parameters:

**Days Parameter** (Inventory History)
- Must be integer
- Valid range: 1-365 days
- Return 400 Bad Request if invalid
- Example error: `{"detail": "days must be between 1 and 365"}`

**Enum Validation** (Order Backlog)
- Status: Only accept `["pending", "processing", "at_risk"]`
- Priority: Only accept `["low", "medium", "high", "critical"]`
- Return 400 Bad Request with allowed values if invalid
- Example error: `{"detail": "status must be one of: pending, processing, at_risk"}`

**Required UUIDs** (Product/Supplier/Route)
- product_id, supplier_id, route_id must be valid UUIDs
- Return 400 Bad Request if format invalid
- May return 404 Not Found if UUID doesn't exist in database
- Example error: `{"detail": "product_id is not a valid UUID format"}`

**Empty Results Handling**
- Return 200 OK with empty array/object `[]` or `{}` instead of 404
- Do NOT throw error for missing data - this is business logic (e.g., product has no history)
- Example: `GET /inventory/history/product-123?days=30` → `{"history": [], "product_id": "product-123"}`

Client-Side Implementation Notes
The agent-side code includes additional validation:

```python
# Example: InventoryHistoryTool validates and rejects invalid days
if not isinstance(days, int) or days < 1 or days > 365:
    raise ValueError("days must be an integer between 1 and 365")
```

This layer catches programming errors before hitting the API. However, the API should still validate to prevent direct API misuse.

Response Format Consistency
All endpoints should return JSON objects with consistent structure:

```json
// Good - consistent structure with metadata
{
  "data": {...},
  "product_id": "uuid",
  "timestamp": "2026-02-18T14:30:00Z",
  "_meta": {
    "api_version": "1.0",
    "response_time_ms": 123
  }
}

// Acceptable - simple data structure
{
  "inventory": [...],
  "summary": {...}
}

// Avoid - inconsistent structure between endpoints
{
  "results": [...],
  "meta": {...}
}
```

Caching Implications
Agent-side caching uses parameter hash + tool name as key. Same parameters will return cached results:

- **Real-time endpoints** (`skip_cache: True`): `get_current_observations`, `get_order_backlog`
  - Called fresh on every agent decision
  - API latency directly impacts response time

- **Historical endpoints** (1 hour cache): `get_inventory_history`
  - Same product_id/days combo cached for 1 hour
  - Reduces unnecessary API calls for trend analysis

- **Analytics endpoints** (10 minute cache): `calculate_stockout_probability`, `calculate_lead_time_risk`
  - Risk metrics cached to avoid recalculation
  - Stale data (10min) acceptable for inventory planning

Example Timeline (Agent Execution):
```
Agent thinks: "I need to analyze product P123"
  ↓
Call get_current_observations() - FRESH (no cache)
  ↓
Call get_inventory_history(product_id="P123", days=30) - CACHE for 1h
  ↓
Call calculate_stockout_probability(product_id="P123") - CACHE for 10m
  ↓
Agent generates decision

2 minutes later...
Another agent thinks the same
  ↓
Call get_current_observations() - FRESH again (real-time)
  ↓
Call get_inventory_history(product_id="P123", days=30) - FROM CACHE ✓
  ↓
Call calculate_stockout_probability(product_id="P123") - FROM CACHE ✓
```
