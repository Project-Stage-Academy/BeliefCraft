# Architecture Overview: BeliefCraft System

## Executive Summary
BeliefCraft is a multi-service system for warehouse analytics with a ReAct-based agent. It combines:
- relational warehouse data in PostgreSQL,
- optional vector infrastructure (Weaviate),
- and an agent service that coordinates tool calls.

## Core Components

### 1. UI Service (`services/ui`)
- Next.js service
- Provides `/health`
- Backend API integration is planned via (`VITE_AGENT_API_URL`, `VITE_ENV_API_URL`, `VITE_RAG_API_URL`)
- Current code implements health route and request tracing middleware; business API calls are not wired yet

### 2. Agent Service (`services/agent-service`)
- FastAPI service on port `8003`
- ReAct workflow implemented via LangGraph (`think -> act -> finalize`)
- LLM calls through AWS Bedrock
- Exposes:
  - `POST /api/v1/agent/analyze`
  - `GET /api/v1/tools`
  - `GET /api/v1/health`

### 3. Environment API (`services/environment-api`)
- FastAPI service on port `8000`
- Smart-query endpoints under `/api/v1/smart-query/*`
- Reads transactional data from PostgreSQL via shared database package

### 4. RAG Service (`services/rag-service`)
- FastAPI service on port `8001`
- Exposes `GET /health` and MCP endpoint `/mcp`
- MCP tools: `search_knowledge_base`, `expand_graph_by_ids`, `get_entity_by_number`, `get_related_code_definitions`
- Current repository backend is `FakeDataRepository` (mock JSON data); Weaviate is provisioned but not wired into runtime retrieval yet

### 5. Data/Infra Services
- PostgreSQL (`5432`) for relational domain data
- Redis (`6379`) for agent caching
- Weaviate (`8080`) provisioned in Docker Compose

## Data Flow (Current Code)
1. Client sends a request to `agent-service` (`/api/v1/agent/analyze`).
2. Agent runs ReAct reasoning and selects tools from local registry.
3. Environment tools call `environment-api` over HTTP (via agent client contracts).
4. RAG tools are loaded from `rag-service` via MCP and called over HTTP/SSE (`/mcp`).
5. Agent returns final answer and reasoning trace.

UI integration status:
- UI to backend business API calls are planned; current UI implementation is limited to `/health` and middleware concerns.

## Notes on MCP
- `rag-service` runs an active MCP server at `/mcp`.
- `agent-service` connects to that MCP server during startup and dynamically registers discovered tools.
- Legacy HTTP RAG client contracts remain in the codebase as deprecated compatibility code.

## Compatibility Note
Client contracts in `agent-service` and implemented routes in downstream services are versioned in the same repo but can diverge during development. Validate route compatibility before assuming end-to-end tool execution.
