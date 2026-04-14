# Agent Service API Reference

## Overview
`agent-service` is a FastAPI service that runs a ReAct loop over a tool registry:
- environment tools are registered locally,
- RAG tools are discovered from `rag-service` MCP endpoint during startup.

Current implementation:
- LLM provider: AWS Bedrock (Claude) via `langchain-aws`
- API prefix: `/api/v1`
- Tool registry includes environment tools and MCP-loaded RAG tools
- Built-in request tracing: `X-Request-ID` header in responses

The repository does **not** implement Bearer-token auth for this service at the API layer.

## Base URL
- Local: `http://localhost:8003`
- API docs: `http://localhost:8003/api/v1/docs`
- OpenAPI JSON: `http://localhost:8003/api/v1/openapi.json`

## Endpoints

### GET `/`
Returns basic service info.

Example response:
```json
{
  "service": "agent-service",
  "version": "0.1.0",
  "status": "running",
  "docs": "/api/v1/docs",
  "health": "/api/v1/health"
}
```

### GET `/api/v1/health`
Returns service health and dependency checks.

Dependencies checked by implementation:
- `environment_api` (`ENVIRONMENT_API_URL + /health`)
- `rag_api` (`RAG_API_URL + /health`)
- `redis`
- `aws_bedrock` (configuration presence)

Example response:
```json
{
  "status": "healthy",
  "service": "agent-service",
  "version": "0.1.0",
  "timestamp": "2026-02-23T21:00:00+00:00",
  "dependencies": {
    "environment_api": "healthy",
    "rag_api": "healthy",
    "redis": "healthy",
    "aws_bedrock": "configured"
  }
}
```

Possible status values include:
- `healthy`, `unhealthy`, `degraded`
- `configured`, `missing_key`, `missing_config`
- `error: ...`

### POST `/api/v1/agent/analyze`
Runs ReAct reasoning for a user query.

Request body (`AgentQueryRequest`):
```json
{
  "query": "What orders are at risk in the next 48 hours?",
  "context": {
    "warehouse_id": "..."
  },
  "max_iterations": 10
}
```

Validation rules:
- `query`: required, `min_length=10`, `max_length=1000`
- `max_iterations`: `1..20`
Example response (`AgentRecommendationResponse`):
```json
{
  "request_id": "...",
  "query": "What orders are at risk in the next 48 hours?",
  "status": "completed",
  "final_answer": "...",
  "task": "...",
  "analysis": "...",
  "iterations": 3,
  "token_usage": {
    "us.anthropic.claude-3-5-sonnet-20240620-v1:0": {
      "prompt": 812,
      "completion": 150,
      "total": 962,
      "cache_read_input_tokens": 0,
      "cache_creation_input_tokens": 0,
      "cache_read_percentage": 0.0,
      "cache_write_percentage": 0.0
    }
  },
  "reasoning_trace": [
    {
      "iteration": 1,
      "thought": "...",
      "actions": [
        {
          "tool": "get_order_backlog",
          "arguments": {
            "status": "pending"
          },
          "observation": {
            "data": []
          }
        },
        {
          "tool": "search_knowledge_base",
          "arguments": {
            "query": "late-order risk heuristic"
          },
          "observation": "Received 2 documents"
        }
      ]
    }
  ],
  "execution_time_seconds": 2.34
}
```

### ModelTokenUsage Schema
| Field | Type | Description |
| :--- | :--- | :--- |
| `prompt` | int | Input tokens not associated with cache |
| `completion` | int | Output tokens generated |
| `total` | int | Combined input and output tokens |
| `cache_read_input_tokens` | int | Input tokens retrieved from LLM cache |
| `cache_creation_input_tokens` | int | Input tokens that resulted in cache creation |
| `cache_read_percentage` | float | percentage of input tokens read from cache |
| `cache_write_percentage` | float | percentage of input tokens that created cache |
Trace shape note:
- single-tool iteration: `reasoning_trace[i].action`
- multi-tool iteration: `reasoning_trace[i].actions`

### GET `/api/v1/tools`
Lists registered tools.

Query parameter:
- `category` (optional): `environment | rag`

Example response:
```json
{
  "tools": [
    {
      "name": "get_current_observations",
      "description": "Get current inventory observations from warehouse sensors.",
      "category": "environment",
      "parameters": {
        "type": "object",
        "properties": {
          "product_id": {"type": "string"}
        },
        "required": []
      }
    }
  ],
  "total_count": 9
}
```

## Registered Tool Set (Current)
Environment tools:
- `get_current_observations`
- `get_order_backlog`
- `get_shipments_in_transit`
- `calculate_stockout_probability`
- `calculate_lead_time_risk`
- `get_inventory_history`

RAG tools:
- `search_knowledge_base`
- `expand_graph_by_ids`
- `get_entity_by_number`

## Downstream Contract Note
The agent tool layer currently uses:
- HTTP client contracts for `environment-api` (`services/agent-service/app/clients/environment_client.py`)
- MCP client contract for `rag-service` (`services/agent-service/app/clients/rag_mcp_client.py`)
- RAG metadata contract for extractor post-processing (`docs/agent-service/RAG_METADATA_CONTRACT.md`)

Deprecated compatibility code for REST RAG client still exists in `services/agent-service/app/clients/rag_client.py`, but active startup path loads RAG tools from MCP.

## Error Handling
- Request validation errors: FastAPI `422`
- Runtime failures in `/api/v1/agent/analyze`: `500` with `{"detail": "Agent execution failed: ..."}`
- Custom service exceptions: JSON shape `{"error", "message", "request_id"}`

## Configuration Keys (from `services/agent-service/.env.example`)
- Service: `SERVICE_NAME`, `SERVICE_VERSION`, `API_V1_PREFIX`, `HOST`, `PORT`
- External URLs: `ENVIRONMENT_API_URL`, `RAG_API_URL`
- Bedrock: `AWS_DEFAULT_REGION`, `BEDROCK_MODEL_ID`, `BEDROCK_TEMPERATURE`, `BEDROCK_MAX_TOKENS`
- Credentials: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`
- Cache/Redis: `REDIS_URL`, `CACHE_TTL_SECONDS`
- Agent loop: `MAX_ITERATIONS`, `TOOL_TIMEOUT_SECONDS`
- Logging: `LOG_LEVEL`
