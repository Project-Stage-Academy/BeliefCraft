# Agent Tools Documentation

## Overview

The BeliefCraft ReAct agent has access to **9 tools** across **2 categories** for warehouse decision support:

| Category | Count | Tools |
|----------|-------|-------|
| **Environment** | 6 | Query warehouse state, orders, shipments, risks |
| **RAG** | 3 | Search knowledge base, retrieve algorithms |

All tools follow OpenAI function calling schema (compatible with Claude, GPT-4, Anthropic Bedrock).

---

## Architecture

```
┌──────────────────────────────────────────────────────┐
│                   ReAct Agent                        │
│         (_think_node, _act_node via tool registry)   │
└────────────────────┬─────────────────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────────────────┐
│              Tool Registry                           │
│  • Registers & discovers tools                       │
│  • Converts to OpenAI function schemas               │
│  • Executes with error handling & logging            │
│  • Supports Redis caching (optional)                 │
└────────┬──────────────────────────────┬──────────────┘
         │                              │
         ▼                              ▼
┌─────────────────────┐        ┌─────────────────────┐
│  Environment Tools  │        │     RAG Tools       │
│  • CachedTool w/    │        │  • CachedTool w/    │
│    Redis caching    │        │    Redis caching    │
│  • TTL: 5m-1h       │        │  • TTL: 24h         │
│  • skip_cache: 2    │        │  • Static content   │
└─────────┬───────────┘        └─────────┬───────────┘
          │                              │
          ▼                              ▼
┌─────────────────────┐        ┌─────────────────────┐
│ Environment API     │        │   RAG Service       │
│ (Port 8000)         │        │   (Port 8001)       │
└─────────────────────┘        └─────────────────────┘
```

---

## Quick Reference: Available Tools

### Environment Tools

| Tool | Description | Parameters |
|------|-------------|------------|
| `get_current_observations` | Current inventory from sensors | product_id, location_id, warehouse_id |
| `get_order_backlog` | Pending orders | warehouse_id, days |
| `get_shipments_in_transit` | Active shipments | warehouse_id |
| `calculate_stockout_probability` | Probability of stockout | product_id, lead_time_days |
| `calculate_lead_time_risk` | Risk assessment by lead time | product_id, warehouse_id |
| `get_inventory_history` | Historical inventory levels | product_id, days |

### RAG Tools

| Tool | Description | Parameters |
|------|-------------|------------|
| `search_knowledge_base` | Semantic search in algorithms book | query (required), k, traverse_types, filters |
| `expand_graph_by_ids` | Retrieve linked entities | document_ids (required), traverse_types |
| `get_entity_by_number` | Get specific numbered entity | entity_type (required), number (required) |

---

## Tool Registry API

### Listing Tools

**Endpoint:** `GET /api/v1/tools`

Lists all available tools with their metadata and parameter schemas.

**Query Parameters:**
```
category: Optional[str]  # Filter by: environment, rag, planning, utility
```

**Response:**
```json
{
  "tools": [
    {
      "name": "get_current_observations",
      "description": "Get current inventory observations from warehouse sensors",
      "category": "environment",
      "parameters": {
        "type": "object",
        "properties": {
          "product_id": {"type": "string", "description": "Filter by product UUID"},
          "location_id": {"type": "string", "description": "Filter by location UUID"},
          "warehouse_id": {"type": "string", "description": "Filter by warehouse UUID"}
        },
        "required": []
      }
    }
  ],
  "total_count": 9
}
```

**Examples:**

```bash
# List all tools
curl http://localhost:8002/api/v1/tools

# Filter by environment category
curl http://localhost:8002/api/v1/tools?category=environment

# Filter by RAG category
curl http://localhost:8002/api/v1/tools?category=rag
```

---

## Integration with ReAct Agent

### Tool Definition Retrieval

Tools are automatically discovered during agent initialization:

```python
from app.services.react_agent import ReActAgent
from app.tools.registry import tool_registry

# Agent automatically loads tool definitions
agent = ReActAgent()

# Tools are available to the LLM in the think node
# via: agent._get_tool_definitions() → tool_registry.get_openai_functions()
```

### Tool Execution Flow

1. **Think Node:** LLM analyzes state and decides which tool to call
2. **Tool Parsing:** Extracts tool name and arguments from LLM response
3. **Act Node:** Executes tool via `tool_registry.execute_tool(name, args)`
4. **Result Format:** Tool result structured as JSON for LLM reasoning

```python
# Inside _execute_tool (react_agent.py - async)
result = await tool_registry.execute_tool(tool_name, arguments)

if result.success:
    return result.data  # Return tool result to LLM
else:
    return {"error": result.error}  # Return error for LLM to reason about
```

### Tool State in ReAct Loop

```
start
  ↓
[THINK] LLM selects tool(s) → tool calls appended to messages
  ↓
[ACT] Execute tool(s) → collect results
  ↓
[THINK] LLM reasons on results → repeat or final answer
  ↓
[FINALIZE] Return final answer + trace
```

---

## Tool Execution Framework

### Base Tool Interface

All tools inherit from `BaseTool` and implement:

```python
from app.tools.base import BaseTool, ToolMetadata
from typing import Any

class MyTool(BaseTool):
    def get_metadata(self) -> ToolMetadata:
        """Define tool name, description, parameters, category"""
        return ToolMetadata(
            name="my_tool",
            description="What this tool does",
            category="utility",  # or: environment, rag, planning
            parameters={
                "type": "object",
                "properties": {
                    "param1": {"type": "string"}
                },
                "required": ["param1"]
            }
        )

    async def execute(self, param1: str, **kwargs: Any) -> dict[str, Any]:
        """Execute tool - return dict or Any serializable to JSON"""
        return {"result": f"Processed {param1}"}
```

### Tool Registration

**Automatic:** Tools are auto-registered on import via `tool_registry` singleton:

```python
# app/tools/__init__.py
from app.tools.registry import tool_registry
from app.tools.environment_tools import (
    GetCurrentObservationsTool,
    GetOrderBacklogTool,
    # ... etc
)

# Registration happens on module import
for tool_cls in [GetCurrentObservationsTool, GetOrderBacklogTool, ...]:
    tool_registry.register(tool_cls())
```

### Tool Result Format

Each tool execution returns:

```python
class ToolResult(BaseModel):
    success: bool                    # Execution succeeded
    data: Any | None                # Result data (if success=True)
    error: str | None               # Error message (if success=False)
    execution_time_ms: float        # Execution duration
    cached: bool                     # Whether result from cache
    timestamp: datetime              # UTC execution time
```

---

## Caching Strategy

### Current Implementation

- **Environment Tools:** Redis cache, TTL 5m-1h (volatile data)
- **RAG Tools:** Redis cache, TTL 24h (static content)
- **skip_cache:** 2 tools always fresh (observations, real-time sensors)

### Cache Configuration

Set via environment:
```bash
CACHE_TTL_DEFAULT=300           # 5 minutes default
CACHE_TTL_ENVIRONMENT=600       # Environment: 10m
CACHE_TTL_RAG=86400             # RAG: 24h
REDIS_URL=redis://localhost:6379/0
```

### Using CachedTool Wrapper

```python
from app.tools.cached_tool import CachedTool
from app.tools.environment_tools import GetCurrentObservationsTool

# Wrap tool with caching
tool = GetCurrentObservationsTool()
cached_tool = CachedTool(tool, ttl=600)

# Execute (will cache result)
result = await cached_tool.run(product_id="P-123")
```

---

## Error Handling

### Tool Execution Errors

Tool errors are caught and returned as structured errors:

```python
try:
    result = await tool.run(**kwargs)
except Exception as e:
    return ToolResult(
        success=False,
        error=str(e),
        execution_time_ms=elapsed
    )
```

### LLM Reasoning on Errors

When a tool fails, the error is returned to the LLM as a tool result:

```json
{
  "role": "tool",
  "tool_call_id": "tc_1",
  "name": "get_inventory",
  "content": "{\"error\": \"Connection timeout\", \"message\": \"Tool execution failed: Connection timeout\"}"
}
```

The LLM can then:
- Retry with different parameters
- Use alternative tools
- Report to user

---

## Adding New Tools

### Step 1: Create Tool Class

```python
# app/tools/my_tools.py
from app.tools.base import BaseTool, ToolMetadata
from typing import Any

class MyNewTool(BaseTool):
    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="my_new_tool",
            description="What this tool does",
            category="utility",  # or environment, rag, planning
            parameters={
                "type": "object",
                "properties": {
                    "param1": {"type": "string", "description": "Input parameter"}
                },
                "required": ["param1"]
            }
        )

    async def execute(self, param1: str, **kwargs: Any) -> dict[str, Any]:
        # Your implementation
        return {"result": f"Processed {param1}"}
```

### Step 2: Register Tool

Add to `app/tools/__init__.py`:

```python
from app.tools.my_tools import MyNewTool

tool_registry.register(MyNewTool())
```

### Step 3: Verify Registration

```bash
curl http://localhost:8002/api/v1/tools | grep my_new_tool
```

---

## Testing Tools

### Unit Test Example

```python
import pytest

@pytest.mark.asyncio
async def test_my_tool() -> None:
    tool = MyNewTool()
    result = await tool.run(param1="test")

    assert result.success
    assert result.data["result"] == "Processed test"
    assert result.execution_time_ms > 0
```

### API Test Example

```python
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_list_tools() -> None:
    response = client.get("/api/v1/tools")
    assert response.status_code == 200
    assert response.json()["total_count"] == 9

def test_filter_by_category() -> None:
    response = client.get("/api/v1/tools?category=environment")
    assert response.status_code == 200
    assert len(response.json()["tools"]) == 6
```

### Integration Test

```bash
# Run API server
uv run uvicorn app.main:app --port 8002

# Test tool endpoint
curl http://localhost:8002/api/v1/tools?category=environment | jq .
```

---

## Debugging Tools

### Enable Tool Logging

```python
import logging
from common.logging import configure_logging

# Enable debug logging
logging.getLogger("app.tools").setLevel(logging.DEBUG)
```

### Inspect Registry

```python
from app.tools.registry import tool_registry

# List all tools
tools = tool_registry.list_tools()
for tool in tools:
    print(f"{tool.metadata.name}: {tool.metadata.description}")

# Get specific tool
tool = tool_registry.get_tool("get_current_observations")
print(f"Parameters: {tool.metadata.parameters}")

# Get statistics
stats = tool_registry.get_registry_stats()
print(f"Total tools: {stats['total_tools']}")
print(f"By category: {stats['by_category']}")
```

### View Tool Execution Logs

```bash
# Run tests with output
uv run pytest tests/test_tools_api.py -v -s

# Run specific test
uv run pytest tests/test_tools_api.py::test_list_tools_all -v -s
```

---

## Files Reference

- **Tool Registry:** `app/tools/registry.py` - Central registry & tool discovery
- **Base Tool:** `app/tools/base.py` - Abstract base class
- **Cached Tool:** `app/tools/cached_tool.py` - Redis caching wrapper
- **Tools API:** `app/api/v1/routes/tools.py` - Listing endpoint
- **ReActAgent:** `app/services/react_agent.py` - Tool execution in agent loop
- **Tests:** `tests/test_tools_api.py` - API endpoint tests

---

**Last Updated:** 2026-02-18
**Version:** 0.2.0
**Status:** ✅ Implemented (9/9 tools + Registry + API endpoint)
