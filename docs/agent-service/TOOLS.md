# Agent Tools Documentation

## Overview

The BeliefCraft ReAct agent has access to **9 tools** across **2 categories** for warehouse decision support:

- **6 Environment Tools**: Query warehouse state, orders, shipments, and calculate risks
- **3 RAG Tools**: Search knowledge base for algorithms and formulas from "Algorithms for Decision Making"

All tools follow OpenAI function calling schema and are compatible with Claude, GPT-4, and other LLMs.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   ReAct Agent                            │
│              (LangGraph State Machine)                   │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│                  Tool Registry                           │
│  • Registers all available tools                        │
│  • Converts to OpenAI function schemas                  │
│  • Executes tools with error handling                   │
└────────┬────────────────────────────────────────┬───────┘
         │                                        │
         ▼                                        ▼
┌──────────────────────┐              ┌──────────────────────┐
│  Environment Tools    │              │    RAG Tools         │
│  (6 tools)           │              │    (3 tools)         │
└──────────┬───────────┘              └──────────┬───────────┘
           │                                     │
           ▼                                     ▼
┌──────────────────────┐              ┌──────────────────────┐
│  EnvironmentAPIClient│              │    RAGAPIClient      │
│  • Retry logic       │              │    • Retry logic     │
│  • Trace propagation │              │    • Trace propagation│
└──────────┬───────────┘              └──────────┬───────────┘
           │                                     │
           ▼                                     ▼
┌──────────────────────┐              ┌──────────────────────┐
│  Environment API     │              │    RAG Service       │
│  (Port 8000)         │              │    (Port 8001)       │
└──────────────────────┘              └──────────────────────┘
```

---

## Environment Tools

Tools for querying warehouse state and performing risk analysis.

### 🔍 get_current_observations

Get current inventory observations from warehouse sensors. Note: observations may be noisy or incomplete.

**Category:** `environment`

**Parameters:**
- `product_id` (string, optional): Filter by specific product UUID
- `location_id` (string, optional): Filter by specific location UUID
- `warehouse_id` (string, optional): Filter by specific warehouse UUID

**Returns:** Dictionary with current observations data

**Example:**
```json
{
  "tool": "get_current_observations",
  "arguments": {
    "product_id": "P-123",
    "warehouse_id": "WH-1"
  }
}
```

**Response:**
```json
{
  "observations": [
    {
      "product_id": "P-123",
      "location_id": "L-456",
      "quantity": 150,
      "timestamp": "2026-02-14T08:00:00Z",
      "sensor_confidence": 0.95
    }
  ],
  "warehouse_id": "WH-1",
  "timestamp": "2026-02-14T08:05:23Z"
}
```

---

### 📋 get_order_backlog

Get current unfulfilled orders with deadlines and priorities. Use to identify at-risk orders.

**Category:** `environment`

**Parameters:**
- `status` (string, optional): Filter by order status
  - Values: `"pending"`, `"processing"`, `"at_risk"`
- `priority` (string, optional): Filter by priority level
  - Values: `"low"`, `"medium"`, `"high"`, `"critical"`

**Returns:** Dictionary with order backlog data

**Example:**
```json
{
  "tool": "get_order_backlog",
  "arguments": {
    "status": "at_risk",
    "priority": "high"
  }
}
```

**Response:**
```json
{
  "orders": [
    {
      "order_id": "O-789",
      "status": "at_risk",
      "priority": "high",
      "deadline": "2026-02-16T00:00:00Z",
      "items": [
        {"product_id": "P-123", "quantity": 100}
      ],
      "risk_score": 0.85
    }
  ],
  "total": 1
}
```

---

### 🚚 get_shipments_in_transit

Get shipments currently in transit (inbound/outbound/transfer). Use to assess incoming inventory.

**Category:** `environment`

**Parameters:**
- `warehouse_id` (string, optional): Filter by destination warehouse UUID

**Returns:** Dictionary with shipment data

**Example:**
```json
{
  "tool": "get_shipments_in_transit",
  "arguments": {
    "warehouse_id": "WH-1"
  }
}
```

**Response:**
```json
{
  "shipments": [
    {
      "shipment_id": "S-456",
      "type": "inbound",
      "origin": "Supplier-X",
      "destination": "WH-1",
      "estimated_arrival": "2026-02-15T14:00:00Z",
      "items": [
        {"product_id": "P-123", "quantity": 500}
      ],
      "status": "in_transit"
    }
  ],
  "total": 1
}
```

---

### ⚠️ calculate_stockout_probability

Calculate the probability that a product will stock out based on current inventory, demand forecast, and lead times.

**Category:** `environment`

**Parameters:**
- `product_id` (string, **required**): Product UUID to analyze

**Returns:** Dictionary with probability (0-1) and risk metrics

**Example:**
```json
{
  "tool": "calculate_stockout_probability",
  "arguments": {
    "product_id": "P-123"
  }
}
```

**Response:**
```json
{
  "product_id": "P-123",
  "probability": 0.35,
  "risk_level": "medium",
  "current_inventory": 150,
  "daily_demand_mean": 25,
  "daily_demand_std": 5,
  "lead_time_days": 7,
  "recommendation": "Consider reordering within 2 days"
}
```

---

### 🕐 calculate_lead_time_risk

Calculate lead time risk (CVaR, tail risk) for suppliers and routes. Use to assess delivery delay probability.

**Category:** `environment`

**Parameters:**
- `supplier_id` (string, optional): Filter by specific supplier UUID
- `route_id` (string, optional): Filter by specific shipping route UUID

**Returns:** Dictionary with lead time statistics and risk metrics

**Example:**
```json
{
  "tool": "calculate_lead_time_risk",
  "arguments": {
    "supplier_id": "SUP-001"
  }
}
```

**Response:**
```json
{
  "supplier_id": "SUP-001",
  "mean_lead_time_days": 14,
  "std_dev": 3.5,
  "percentile_95": 20,
  "cvar_95": 21.5,
  "reliability_score": 0.85,
  "historical_deliveries": 156,
  "risk_assessment": "moderate"
}
```

---

### 📊 get_inventory_history

Get historical inventory levels and movements for a product. Use to analyze trends and seasonality.

**Category:** `environment`

**Parameters:**
- `product_id` (string, **required**): Product UUID to retrieve history for
- `days` (integer, optional): Number of days to look back
  - Default: `30`
  - Range: `1-365`

**Returns:** Dictionary with historical inventory data

**Example:**
```json
{
  "tool": "get_inventory_history",
  "arguments": {
    "product_id": "P-123",
    "days": 60
  }
}
```

**Response:**
```json
{
  "product_id": "P-123",
  "days": 60,
  "history": [
    {
      "date": "2026-01-15",
      "quantity": 200,
      "inbound": 500,
      "outbound": 300,
      "adjustments": 0
    }
  ],
  "statistics": {
    "min": 50,
    "max": 500,
    "mean": 175,
    "trend": "stable"
  }
}
```

---

## RAG Tools

Tools for searching the knowledge base and retrieving algorithms from "Algorithms for Decision Making".

### 🔎 search_knowledge_base

Semantic search across "Algorithms for Decision Making" book for relevant algorithms, formulas, and concepts.

**Category:** `rag`

**Parameters:**
- `query` (string, **required**): Natural language search query
  - Examples: `"inventory control under uncertainty"`, `"POMDP belief state update"`, `"CVaR risk assessment"`
- `k` (integer, optional): Number of results to return
  - Default: `5`
  - Range: `1-20`
- `traverse_types` (array, optional): Types of linked entities to auto-retrieve
  - Examples: `["formula", "algorithm_code"]`
- `filters` (object, optional): Metadata filters
  - Properties: `chapter` (string), `section` (string), `page_number` (integer)

**Returns:** Dictionary with search results and metadata

**Example:**
```json
{
  "tool": "search_knowledge_base",
  "arguments": {
    "query": "POMDP belief state update",
    "k": 3,
    "traverse_types": ["formula", "algorithm_code"],
    "filters": {"chapter": "16"}
  }
}
```

**Response:**
```json
{
  "results": [
    {
      "id": "chunk_16_4_2",
      "text": "The belief state is updated using Bayesian inference...",
      "score": 0.95,
      "metadata": {
        "chapter": "16",
        "section": "16.4",
        "page": 342,
        "title": "Belief State Representations"
      },
      "linked_entities": [
        {
          "type": "formula",
          "number": "16.4",
          "content": "b'(s') = η P(o|s') Σ_s P(s'|s,a) b(s)"
        }
      ]
    }
  ],
  "total": 3,
  "query_time_ms": 120
}
```

---

### 🔗 expand_graph_by_ids

Retrieve linked entities (formulas, algorithms, tables) from specific document IDs. Use after search to get complete context.

**Category:** `rag`

**Parameters:**
- `document_ids` (array, **required**): List of document/chunk IDs to expand from
- `traverse_types` (array, optional): Types of entities to retrieve
  - Examples: `["formula", "algorithm_code", "table", "image"]`

**Returns:** Dictionary with expanded entities and relationships

**Example:**
```json
{
  "tool": "expand_graph_by_ids",
  "arguments": {
    "document_ids": ["chunk_16_4_2", "chunk_16_4_3"],
    "traverse_types": ["formula", "algorithm_code"]
  }
}
```

**Response:**
```json
{
  "expanded": [
    {
      "id": "formula_16_4",
      "type": "formula",
      "content": "b'(s') = η P(o|s') Σ_s P(s'|s,a) b(s)",
      "title": "Bayesian Belief Update",
      "chapter": "16"
    },
    {
      "id": "algo_16_2",
      "type": "algorithm",
      "number": "16.2",
      "title": "POMDP Value Iteration",
      "code": "function pomdp_value_iteration()..."
    }
  ],
  "relationships": [
    {
      "from": "chunk_16_4_2",
      "to": "formula_16_4",
      "type": "REFERENCES"
    }
  ]
}
```

---

### 📖 get_entity_by_number

Retrieve a specific numbered entity from the book by its exact number (e.g., Algorithm 3.2, Formula 16.4).

**Category:** `rag`

**Parameters:**
- `entity_type` (string, **required**): Type of entity
  - Values: `"formula"`, `"table"`, `"algorithm"`, `"figure"`
- `number` (string, **required**): Entity number as it appears in the book
  - Examples: `"3.2"`, `"16.4"`, `"5.1"`, `"12.3a"`

**Returns:** Dictionary with entity content and metadata

**Example:**
```json
{
  "tool": "get_entity_by_number",
  "arguments": {
    "entity_type": "algorithm",
    "number": "3.2"
  }
}
```

**Response:**
```json
{
  "entity_type": "algorithm",
  "number": "3.2",
  "title": "(s,S) Inventory Policy",
  "content": "function inventory_policy(inventory, s, S):\n    if inventory < s:\n        order = S - inventory\n    else:\n        order = 0\n    return order",
  "description": "Two-parameter inventory control policy...",
  "chapter": "3",
  "section": "3.2",
  "page": 45
}
```

---

## Tool Execution Flow

### 1. Tool Registration

```python
from app.tools.registry import tool_registry
from app.tools.environment_tools import GetCurrentObservationsTool

# Register tool
tool = GetCurrentObservationsTool()
tool_registry.register(tool)

# Get OpenAI function schema
functions = tool_registry.get_openai_functions(categories=["environment"])
```

### 2. Tool Execution

```python
# Execute via registry
result = await tool_registry.execute_tool(
    "get_current_observations",
    {"product_id": "P-123"}
)

# Result contains:
# - success: bool
# - data: tool-specific response
# - error: error message if failed
# - execution_time_ms: performance metric
```

### 3. Error Handling

All tools automatically handle:
- ✅ Network errors (retry with exponential backoff)
- ✅ Timeout errors (configurable timeout)
- ✅ API errors (proper error messages)
- ✅ Validation errors (parameter validation)

---

## Caching Strategy

### Current Implementation
❌ **Not yet implemented** - Planned for future optimization

### Planned Caching (Redis)

**Environment Tools:**
- TTL: `1-10 minutes` (dynamic data)
- Cache key: `tool:{tool_name}:{hash(params)}`
- Invalidation: Time-based expiration

**RAG Tools:**
- TTL: `1-2 hours` (static content)
- Cache key: `rag:{tool_name}:{hash(params)}`
- Invalidation: Manual + time-based

**Example:**
```python
# Cache key generation
cache_key = f"tool:get_current_observations:{hash_params(product_id='P-123')}"

# Check cache
cached = await redis.get(cache_key)
if cached:
    return cached

# Execute and cache
result = await client.get_current_observations(...)
await redis.setex(cache_key, ttl=300, value=result)
```

---

## Performance Metrics

| Tool | Avg Response Time | p95 | Retry Rate |
|------|------------------|-----|------------|
| `get_current_observations` | 150ms | 300ms | 2% |
| `get_order_backlog` | 180ms | 350ms | 2% |
| `get_shipments_in_transit` | 120ms | 250ms | 1% |
| `calculate_stockout_probability` | 500ms | 1000ms | 3% |
| `calculate_lead_time_risk` | 450ms | 900ms | 3% |
| `get_inventory_history` | 300ms | 600ms | 2% |
| `search_knowledge_base` | 800ms | 1500ms | 5% |
| `expand_graph_by_ids` | 400ms | 800ms | 4% |
| `get_entity_by_number` | 200ms | 400ms | 2% |

*Note: Metrics are estimates and will be collected after deployment*

---

## Troubleshooting

### Tool Execution Failures

**Problem:** Tool returns `success: false`

**Check:**
1. ✅ External service is running (Environment API, RAG Service)
2. ✅ Network connectivity between services
3. ✅ Tool parameters are valid (check required fields)
4. ✅ Service logs for detailed error messages

**Example:**
```bash
# Check service health
curl http://environment-api:8000/health
curl http://rag-service:8001/health

# View logs
docker-compose logs environment-api
docker-compose logs rag-service
```

---

### High Response Times

**Problem:** Tool execution > 5 seconds

**Check:**
1. ✅ External API performance (check API logs)
2. ✅ Network latency between services
3. ✅ Large result sets (reduce `k` parameter for RAG tools)
4. ✅ Database query performance (Environment API)

**Solution:**
```python
# Use timeout parameter
result = await tool_registry.execute_tool(
    "search_knowledge_base",
    {"query": "...", "k": 3},  # Reduce k
    timeout=5.0  # Override default timeout
)
```

---

### Missing Data in Responses

**Problem:** Tool returns empty results

**Environment Tools:**
- ✅ Check if data exists in warehouse database
- ✅ Verify filter parameters (product_id, warehouse_id)
- ✅ Check Environment API logs for errors

**RAG Tools:**
- ✅ Verify knowledge base is indexed
- ✅ Try broader search query
- ✅ Remove restrictive filters
- ✅ Check RAG Service logs

---

### Tools Not Registered

**Problem:** Agent can't find tool

**Check:**
```python
# List all registered tools
from app.tools.registry import tool_registry

tools = tool_registry.get_tool_names()
print(f"Registered tools: {tools}")

# Get registry stats
stats = tool_registry.get_registry_stats()
print(f"Total: {stats['total_tools']}")
print(f"By category: {stats['by_category']}")
```

**Solution:** Ensure tools are registered at application startup in `app/main.py`

---

## Testing Tools

### Unit Tests

```bash
# Test environment tools
uv run pytest tests/test_environment_tools.py -v

# Test RAG tools
uv run pytest tests/test_rag_tools.py -v

# Test all tools
uv run pytest tests/test_*_tools.py -v
```

### Integration Tests

```bash
# Test with real services (requires running Environment API and RAG Service)
uv run pytest tests/integration/test_tools_integration.py -v
```

### Manual Testing

```python
# Test tool directly
from app.tools.environment_tools import GetCurrentObservationsTool

tool = GetCurrentObservationsTool()
result = await tool.run(product_id="P-123")

print(f"Success: {result.success}")
print(f"Data: {result.data}")
print(f"Time: {result.execution_time_ms}ms")
```

---

## See Also

- [Agent Architecture](./ARCHITECTURE.md) - Overall agent design
- [API Documentation](./API.md) - Agent service API endpoints
- [Configuration](./CONFIGURATION.md) - Tool configuration options
- [Logging Best Practices](../logging-best-practices.md) - Structured logging

---

**Last Updated:** 2026-02-14
**Version:** 0.1.0
**Status:** ✅ Implemented (9/9 tools)
