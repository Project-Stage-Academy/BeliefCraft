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
│   CachedTool (6)     │              │   CachedTool (3)     │
│  Environment Tools   │              │     RAG Tools        │
│  • Redis caching     │              │   • Redis caching    │
│  • TTL: 5m-1h        │              │   • TTL: 24h         │
│  • skip_cache: 2     │              │   • Static content   │
└──────────┬───────────┘              └──────────┬───────────┘
           │                                     │
           ├──────────┬──────────────────────────┤
           │          ▼                          │
           │   ┌─────────────┐                  │
           │   │    Redis    │                  │
           │   │  Cache Store│                  │
           │   └─────────────┘                  │
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

**Key Components:**
- **CachedTool**: Transparent wrapper for Redis caching
- **Redis**: Cache backend for tool results
- **skip_cache: 2**: Real-time tools (observations, orders) always fresh
- **TTL Strategy**: 5min → 1h → 24h based on data volatility

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

### 1. Tool Registration (Automatic on Import)

```python
# app/tools/__init__.py - auto-executes on import
from app.tools import tool_registry

# All 9 tools are already registered with caching!
# No manual registration needed

# Tools are wrapped with CachedTool automatically:
# tool_registry.register(CachedTool(GetCurrentObservationsTool()))
# tool_registry.register(CachedTool(SearchKnowledgeBaseTool()))
# etc.

# Get OpenAI function schemas
functions = tool_registry.get_openai_functions(categories=["environment"])
```

### 2. Tool Execution (With Caching)

```python
# Execute via registry
result = await tool_registry.execute_tool(
    "search_knowledge_base",
    {"query": "POMDP algorithms", "k": 5}
)

# Result contains:
# - success: bool - execution status
# - data: dict - tool-specific response
# - error: str | None - error message if failed
# - execution_time_ms: float - performance metric
# - cached: bool - True if result from cache
# - timestamp: datetime - execution timestamp
```

### 3. Caching Flow

```
Request → Tool Registry → CachedTool
                            │
                            ├─ Check Redis Cache
                            │   │
                            │   ├─ Cache HIT ✅
                            │   │   └─ Return cached result (instant)
                            │   │
                            │   └─ Cache MISS ❌
                            │       │
                            │       ├─ Execute original tool
                            │       ├─ Store result in Redis (TTL)
                            │       └─ Return fresh result
                            │
                            └─ skip_cache=True (real-time)
                                └─ Execute directly (no cache)
```

### 4. Error Handling

All tools automatically handle:
- ✅ Network errors (retry with exponential backoff)
- ✅ Timeout errors (configurable timeout)
- ✅ API errors (proper error messages)
- ✅ Validation errors (parameter validation)
- ✅ **Cache errors** (graceful degradation - execution continues)

**Cache Error Example:**
```python
# Redis is down - tool still works!
result = await tool_registry.execute_tool("search_knowledge_base", {...})
# Logs warning: "cache_read_error"
# Executes tool normally
# Returns result (without caching)
```

---

## Caching Strategy

### Current Implementation
✅ **Fully implemented** - Redis-based caching with `CachedTool` wrapper

All tools are automatically wrapped with `CachedTool` on registration, providing transparent Redis caching with:
- ✅ Automatic cache key generation from parameters
- ✅ Configurable TTL per tool category
- ✅ Selective caching with `skip_cache` flag
- ✅ Graceful degradation (cache errors don't break execution)
- ✅ Cache hit/miss logging for monitoring

---

### Cache Configuration

**TTL Constants** (defined in `app.core.constants`):

| Constant | Value | Use Case |
|----------|-------|----------|
| `CACHE_TTL_RAG_TOOLS` | 86400s (24h) | Static knowledge from books |
| `CACHE_TTL_HISTORY` | 3600s (1h) | Historical data doesn't change |
| `CACHE_TTL_ANALYTICS` | 600s (10min) | Analytics/risk calculations |
| `CACHE_TTL_SHIPMENTS` | 300s (5min) | Shipments change slowly |

---

### Tool-Specific Caching

#### **Real-Time Tools** (Skip Cache)
These tools always fetch fresh data to avoid stale sensor readings:

- ✅ `get_current_observations` - Real-time warehouse sensors
- ✅ `get_order_backlog` - Live order status

**Configuration:**
```python
# In tool metadata
ToolMetadata(
    name="get_current_observations",
    skip_cache=True,  # Never cache
    ...
)
```

#### **Short TTL Tools** (5-10 minutes)
Semi-dynamic data with moderate change frequency:

- ✅ `get_shipments_in_transit` - **5 minutes** (shipments update slowly)
- ✅ `calculate_stockout_probability` - **10 minutes** (analytics are semi-stable)
- ✅ `calculate_lead_time_risk` - **10 minutes** (supplier stats change slowly)

**Configuration:**
```python
# In tool metadata
ToolMetadata(
    name="calculate_lead_time_risk",
    cache_ttl=CACHE_TTL_ANALYTICS,  # 600 seconds
    ...
)
```

#### **Long TTL Tools** (1-24 hours)
Historical or static data:

- ✅ `get_inventory_history` - **1 hour** (past data is immutable)
- ✅ `search_knowledge_base` - **24 hours** (book content doesn't change)
- ✅ `expand_graph_by_ids` - **24 hours** (static knowledge graph)
- ✅ `get_entity_by_number` - **24 hours** (book entities are static)

**Configuration:**
```python
# In tool metadata
ToolMetadata(
    name="search_knowledge_base",
    cache_ttl=CACHE_TTL_RAG_TOOLS,  # 86400 seconds
    ...
)
```

---

### Implementation Details

#### **Cache Key Generation**

Cache keys are generated using MD5 hash of sorted parameters:

```python
# Format: tool_cache:{tool_name}:{md5_hash_of_params}
cache_key = f"tool_cache:search_knowledge_base:a3d5f8b2..."

# Parameters are sorted for consistency
params = {"query": "POMDP", "k": 5}
# Same as {"k": 5, "query": "POMDP"} - generates identical key
```

#### **CachedTool Wrapper**

All tools are wrapped on registration:

```python
from app.tools import tool_registry, CachedTool
from app.tools.rag_tools import SearchKnowledgeBaseTool

# Automatic wrapping (done in app/tools/__init__.py)
tool_registry.register(CachedTool(SearchKnowledgeBaseTool()))

# TTL comes from tool metadata (cache_ttl field)
# Or falls back to global CACHE_TTL_SECONDS from settings
```

#### **Graceful Degradation**

Cache errors never break tool execution:

```python
# If Redis read fails → execute tool normally
# If Redis write fails → return result anyway
# Errors are logged but don't raise exceptions

logger.warning("cache_read_error", error=str(e))
# Continue to execute tool...
```

---

### Usage Examples

#### **Check if Result was Cached**

```python
result = await tool_registry.execute_tool(
    "search_knowledge_base",
    {"query": "inventory control", "k": 5}
)

if result.cached:
    print(f"✅ Cache hit! (saved {result.execution_time_ms}ms)")
else:
    print(f"❌ Cache miss (executed in {result.execution_time_ms}ms)")
```

#### **Force Cache Bypass** (For Testing)

Real-time tools automatically skip cache. For cached tools, use skip_cache:

```python
# Tools with skip_cache=True always execute fresh
tool = GetCurrentObservationsTool()  # Has skip_cache=True
result = await tool.run(product_id="P-123")  # Always fresh
```

#### **Custom TTL Override**

```python
# Override TTL at wrapper creation (for special cases)
custom_cached_tool = CachedTool(
    SearchKnowledgeBaseTool(),
    ttl_seconds=1800  # 30 minutes instead of 24 hours
)
```

---

### Monitoring Cache Performance

#### **Logs**

Cache operations are automatically logged:

```json
{
  "event": "tool_cache_hit",
  "tool": "search_knowledge_base",
  "cache_key": "tool_cache:search_knowledge_base:a3d5f8b2...",
  "level": "info"
}

{
  "event": "tool_cache_miss",
  "tool": "calculate_lead_time_risk",
  "level": "info"
}

{
  "event": "cache_write_error",
  "tool": "get_inventory_history",
  "error": "Redis connection timeout",
  "level": "warning"
}
```

#### **View Cache Hits in Logs**

```bash
# Filter cache hits
docker-compose logs agent-service | grep "tool_cache_hit"

# Count cache hit rate
docker-compose logs agent-service | jq 'select(.event | contains("cache"))' | wc -l
```

---

### Redis Configuration

#### **Environment Variables**

```bash
# .env or docker-compose.yml
REDIS_URL=redis://localhost:6379
CACHE_TTL_SECONDS=3600  # Global default (1 hour)
```

#### **Redis Memory Management**

Redis uses TTL-based expiration - keys auto-delete after TTL:

```bash
# Check cache keys
redis-cli KEYS "tool_cache:*"

# Check TTL for specific key
redis-cli TTL "tool_cache:search_knowledge_base:a3d5f8b2..."

# Manual cache flush (debugging)
redis-cli FLUSHDB
```

---

### Testing Caching

#### **Unit Tests**

```bash
# Test caching logic
uv run pytest tests/test_cached_tool.py -v

# Test registration with caching
uv run pytest tests/test_tool_registration.py -v
```

#### **Integration Tests**

```python
# Test cache hit scenario
result1 = await tool_registry.execute_tool("search_knowledge_base", {"query": "POMDP"})
assert not result1.cached  # First call - cache miss

result2 = await tool_registry.execute_tool("search_knowledge_base", {"query": "POMDP"})
assert result2.cached  # Second call - cache hit
assert result2.data == result1.data  # Same data
```

---

### Benefits

✅ **Performance**: 10-100x faster for cached results (no API call)
✅ **Reliability**: Reduces load on external services
✅ **Cost**: Fewer API calls to Environment/RAG services
✅ **Consistency**: Same parameters return same results within TTL
✅ **Transparency**: Zero code changes needed in tools or agent

---

### Troubleshooting

#### **Cache Not Working**

**Check Redis connection:**
```bash
docker-compose ps redis
redis-cli PING  # Should return PONG
```

**Check cache configuration:**
```python
from app.tools import tool_registry

tool = tool_registry.get_tool("search_knowledge_base")
metadata = tool.get_metadata()
print(f"TTL: {metadata.cache_ttl}")
print(f"Skip cache: {metadata.skip_cache}")
```

#### **High Cache Miss Rate**

- ✅ Check if parameters are consistent (order matters in some cases)
- ✅ Verify TTL isn't too short
- ✅ Check Redis memory isn't full (keys being evicted)

#### **Stale Data Issues**

- ✅ Reduce TTL for affected tool
- ✅ Consider adding `skip_cache=True` for real-time data
- ✅ Implement manual cache invalidation (future feature)

---

## Performance Metrics

### Without Cache (Cold Execution)

| Tool | Avg Response Time | p95 | Retry Rate | Cache Strategy |
|------|------------------|-----|------------|----------------|
| `get_current_observations` | 150ms | 300ms | 2% | ⚡ No cache (real-time) |
| `get_order_backlog` | 180ms | 350ms | 2% | ⚡ No cache (real-time) |
| `get_shipments_in_transit` | 120ms | 250ms | 1% | 🟢 5 min TTL |
| `calculate_stockout_probability` | 500ms | 1000ms | 3% | 🟢 10 min TTL |
| `calculate_lead_time_risk` | 450ms | 900ms | 3% | 🟢 10 min TTL |
| `get_inventory_history` | 300ms | 600ms | 2% | 🟡 1 hour TTL |
| `search_knowledge_base` | 800ms | 1500ms | 5% | 🔵 24 hour TTL |
| `expand_graph_by_ids` | 400ms | 800ms | 4% | 🔵 24 hour TTL |
| `get_entity_by_number` | 200ms | 400ms | 2% | 🔵 24 hour TTL |

### With Cache (Hot Execution)

| Tool | Cache Hit Time | Speedup | Expected Hit Rate |
|------|----------------|---------|-------------------|
| `get_shipments_in_transit` | ~2ms | **60x faster** | 70-80% |
| `calculate_stockout_probability` | ~2ms | **250x faster** | 60-70% |
| `calculate_lead_time_risk` | ~2ms | **225x faster** | 60-70% |
| `get_inventory_history` | ~2ms | **150x faster** | 80-90% |
| `search_knowledge_base` | ~2ms | **400x faster** | 90-95% |
| `expand_graph_by_ids` | ~2ms | **200x faster** | 85-90% |
| `get_entity_by_number` | ~2ms | **100x faster** | 95-98% |

**Cache Hit Performance:**
- ✅ Redis lookup: ~1-3ms
- ✅ No network calls to external services
- ✅ No API processing time
- ✅ Instant JSON deserialization

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

### Cache Debugging

**Problem:** Unexpected cache behavior

**Check cache status:**
```bash
# Connect to Redis
docker exec -it <redis-container> redis-cli

# List all tool cache keys
KEYS "tool_cache:*"

# Check TTL for specific key
TTL "tool_cache:search_knowledge_base:a3d5f8b2..."

# Get cached value
GET "tool_cache:search_knowledge_base:a3d5f8b2..."

# Flush cache (testing only!)
FLUSHDB
```

**Check cache logs:**
```bash
# Filter cache-related logs
docker-compose logs agent-service | grep cache

# Count cache hits vs misses
docker-compose logs agent-service | grep "tool_cache_hit" | wc -l
docker-compose logs agent-service | grep "tool_cache_miss" | wc -l
```

**Verify tool cache configuration:**
```python
from app.tools import tool_registry

tool = tool_registry.get_tool("search_knowledge_base")
metadata = tool.get_metadata()
print(f"Tool: {metadata.name}")
print(f"TTL: {metadata.cache_ttl}s")
print(f"Skip cache: {metadata.skip_cache}")
```

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
print(f"Cached: {result.cached}")
```

### Cache Tests

```bash
# Test caching logic
uv run pytest tests/test_cached_tool.py -v

# Test tool registration with caching
uv run pytest tests/test_tool_registration.py -v
```

---

## See Also

- [Agent Architecture](./ARCHITECTURE.md) - Overall agent design
- [API Documentation](./API.md) - Agent service API endpoints
- [Configuration](./CONFIGURATION.md) - Tool configuration options
- [Logging Best Practices](../logging-best-practices.md) - Structured logging
- `app/tools/cached_tool.py` - Caching implementation
- `app/tools/__init__.py` - Tool registration

---

**Last Updated:** 2026-02-16
**Version:** 0.1.0
**Status:** ✅ Implemented (9/9 tools + Redis caching)
