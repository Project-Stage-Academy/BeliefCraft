# Logging Best Practices - BeliefCraft

## 📋 Overview

All BeliefCraft services use **structured JSON logging** for consistency, debugging, and monitoring.

**Key Features:**
- JSON output (easy to parse/aggregate)
- Automatic trace_id propagation across services
- Request/response logging with performance metrics
- Error tracking with stack traces
- Configurable log levels via environment variables

---

## 🚀 Quick Start

### 0. Install Common Package

**Before using logging, install the shared package:**

```bash
# For development (includes pytest)
pip install -e packages/common[dev]

# For production (runtime only)
pip install -e packages/common
```

**What does this do?**
- `-e` = editable mode (changes apply immediately)
- `[dev]` = includes pytest, pytest-asyncio for testing
- Installs: structlog, httpx, fastapi

### 1. Setup Logging in Your Service

```python
# services/agent-service/main.py
import os
from fastapi import FastAPI
from common.logging import configure_logging, get_logger
from common.middleware import setup_logging_middleware

# Configure logging (once at startup)
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
configure_logging("agent-service", LOG_LEVEL)

# Create app
app = FastAPI()

# Add logging middleware
setup_logging_middleware(app)

# Get logger for this module
logger = get_logger(__name__)

@app.get("/")
async def root():
    logger.info("root_endpoint_accessed", user_id=123)
    return {"message": "Hello"}
```

### 2. Environment Variables

```bash
# .env
LOG_LEVEL=INFO  # Options: DEBUG, INFO, WARNING, ERROR, CRITICAL
```

---

## 📝 Logging Examples

### Basic Logging

```python
from common.logging import get_logger

logger = get_logger(__name__)

# Info logging with metadata
logger.info(
    "user_login",
    user_id=123,
    username="john_doe",
    login_method="oauth"
)

# Warning for unusual situations
logger.warning(
    "high_latency_detected",
    duration_ms=5000,
    threshold_ms=1000,
    endpoint="/api/v1/query"
)

# Error logging with exception
try:
    result = risky_operation()
except Exception as e:
    logger.error(
        "operation_failed",
        operation="risky_operation",
        error=str(e),
        exc_info=True  # ✅ Include stack trace
    )
```

### Output Example

```json
{
  "timestamp": "2026-02-10T18:30:45.123Z",
  "level": "info",
  "service": "agent-service",
  "logger": "agent_service.main",
  "event": "user_login",
  "user_id": 123,
  "username": "john_doe",
  "login_method": "oauth",
  "trace_id": "abc-123-def-456",
  "client_ip": "192.168.1.100",
  "method": "POST",
  "path": "/api/v1/login"
}
```

---

## 🔗 Request Tracing (Cross-Service)

### Problem
When `agent-service` calls `rag-service` calls `environment-api`, how to trace one request through all services?

### Solution: TracedHttpClient

Use `TracedHttpClient` for all HTTP calls between services to automatically propagate trace_id:

#### Basic Usage

```python
from common.http_client import TracedHttpClient

async def call_rag_service(query: str):
    """Call RAG service with automatic trace_id propagation."""
    async with TracedHttpClient("http://rag-service:8000") as client:
        response = await client.post(
            "/api/search",
            json={"query": query, "top_k": 5}
        )
        return response.json()
```

#### Features

- **Automatic X-Request-ID propagation**: Reads trace_id from structlog context (set by middleware) and injects it into every outgoing request
- **Request/response logging**: Automatically logs method, URL, status code, duration
- **Error logging**: Captures failed requests (4xx/5xx) with response body
- **Async context manager**: Proper connection pool cleanup

#### Example: Agent Calling RAG

```python
# services/agent-service/api/endpoints.py
from common.http_client import TracedHttpClient
from common.logging import get_logger

logger = get_logger(__name__)

@router.post("/agent/action")
async def execute_action(request: ActionRequest):
    """Agent endpoint that calls RAG service."""
    
    # Current trace_id is already in context (set by middleware)
    logger.info("executing_agent_action", action_type=request.action)
    
    # HTTP client automatically reads trace_id from context and adds X-Request-ID header
    async with TracedHttpClient("http://rag-service:8000", timeout=15.0) as client:
        rag_response = await client.post(
            "/api/documents/search",
            json={"query": request.query}
        )
        documents = rag_response.json()
    
    logger.info("rag_search_completed", doc_count=len(documents))
    return {"documents": documents}
```

**All logs will contain same `trace_id`:**
```bash
# Agent service
{"trace_id": "abc-123", "service": "agent-service", "event": "executing_agent_action"}
{"trace_id": "abc-123", "service": "agent-service", "event": "http_request_started"}

# RAG service (same trace_id!)
{"trace_id": "abc-123", "service": "rag-service", "event": "http_request_received"}
{"trace_id": "abc-123", "service": "rag-service", "event": "search_started"}

# All services share the same trace_id for end-to-end tracing
```

#### Debugging Cross-Service Calls

Filter logs by trace_id to see the complete request flow:

```bash
# Show all logs for a specific request across all services
docker-compose logs | grep "abc-123-def"

# Example output:
# rag-service    | {"event": "http_request_received", "trace_id": "abc-123-def", "method": "POST", "path": "/api/v1/query"}
# agent-service  | {"event": "http_request_started", "trace_id": "abc-123-def", "url": "http://rag-service:8000/search"}
# agent-service  | {"event": "http_request_completed", "trace_id": "abc-123-def", "status_code": 200, "duration_ms": 234}
```

#### All HTTP Methods Supported

```python
async with TracedHttpClient("http://environment-api:8000") as client:
    # GET
    state = await client.get("/api/state/current")
    
    # POST
    result = await client.post("/api/action", json={"type": "move"})
    
    # PUT
    updated = await client.put("/api/config/123", json={"setting": "new"})
    
    # PATCH
    patched = await client.patch("/api/partial/456", json={"field": "value"})
    
    # DELETE
    await client.delete("/api/resource/789")
```

#### Configuration

```python
# Custom timeout
async with TracedHttpClient("http://slow-service", timeout=30.0) as client:
    response = await client.get("/slow-endpoint")

# Additional httpx options
async with TracedHttpClient(
    "http://service",
    timeout=10.0,
    verify=False,  # Disable SSL verification (dev only!)
    follow_redirects=True
) as client:
    response = await client.get("/endpoint")
```

#### DO ✅

- Use `TracedHttpClient` for **all** inter-service HTTP calls
- Use async context manager (`async with`)
- Set reasonable timeouts (default 10s)
- Let the client handle trace_id automatically

#### DON'T ❌

- Don't use plain `httpx.AsyncClient` for inter-service calls (loses trace_id)
- Don't manually add X-Request-ID headers (client does this)
- Don't forget timeout (can hang indefinitely)
- Don't call HTTP methods outside `async with` block

---

## 🎯 What to Log

### ✅ DO Log:

**User Actions:**
```python
logger.info("user_action", user_id=123, action="update_inventory", product_id="P001")
```

**Performance Metrics:**
```python
logger.info("query_completed", duration_ms=450, rows_returned=15)
```

**Business Events:**
```python
logger.info("order_created", order_id="O123", total_amount=1500)
```

**Errors with Context:**
```python
logger.error("payment_failed", user_id=123, amount=100, reason="insufficient_funds")
```

**External API Calls:**
```python
logger.info("external_api_call", service="openai", endpoint="/completions", duration_ms=2300)
```

### ❌ DON'T Log:

**Sensitive Data:**
```python
# BAD - don't log passwords, tokens, credit cards
logger.info("user_login", password="secret123")  # ❌

# GOOD - log event without secrets
logger.info("user_login", user_id=123)  # ✅
```

**Too Verbose (in production):**
```python
# BAD - logs every iteration
for item in items:
    logger.debug(f"processing {item}")  # ❌ Use DEBUG level

# GOOD - log summary
logger.info("batch_processed", total_items=len(items), duration_ms=1500)  # ✅
```

**Health Checks (filtered automatically):**
```python
# Automatically excluded: /health, /metrics, /docs
```

---

## 🐛 Debugging

### View Logs in Development

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f agent-service

# Grep by trace_id
docker-compose logs | grep "abc-123-def-456"

# Grep errors only
docker-compose logs | grep '"level":"error"'
```

### Parse JSON Logs (jq)

```bash
# Pretty print
docker-compose logs agent-service | jq '.'

# Filter by trace_id
docker-compose logs | jq 'select(.trace_id == "abc-123")'

# Show only errors
docker-compose logs | jq 'select(.level == "error")'

# Average duration
docker-compose logs | jq '.duration_ms' | awk '{sum+=$1; count++} END {print sum/count}'
```

---

## 🔧 Configuration

### Log Levels

| Level | When to Use | Example |
|-------|-------------|---------|
| **DEBUG** | Development debugging | `logger.debug("variable_state", x=10, y=20)` |
| **INFO** | Normal operations | `logger.info("request_processed", duration_ms=150)` |
| **WARNING** | Unusual but handled | `logger.warning("retry_attempt", attempt=3, max=5)` |
| **ERROR** | Errors requiring attention | `logger.error("db_connection_failed", exc_info=True)` |
| **CRITICAL** | System failure | `logger.critical("service_shutdown", reason="oom")` |

### Change Log Level

```bash
# Development
LOG_LEVEL=DEBUG docker-compose up

# Production
LOG_LEVEL=WARNING docker-compose up
```

---

## 📊 Monitoring & Alerts

### Key Metrics to Track

**Request Duration (P95, P99):**
```python
logger.info("http_request_finished", duration_ms=duration, status_code=200)
```

**Error Rate:**
```python
logger.error("operation_failed", operation="query_rag", error_type="TimeoutError")
```

**Business Metrics:**
```python
logger.info("recommendation_generated", product_id="P001", confidence=0.92)
```

### Aggregation (Future: Prometheus/Grafana)

Current MVP: Parse JSON logs manually  
Future: Send logs to aggregation service (ELK, Loki, etc.)

---

## ✅ Acceptance Criteria Checklist

- [x] All services use structured JSON logging
- [x] Logs include: timestamp, service, level, trace_id, message, metadata
- [x] Log levels configurable via `LOG_LEVEL` environment variable
- [x] Request tracing with correlation IDs (`X-Request-ID` header)
- [x] Logs aggregated in `docker-compose logs`
- [x] Error tracking captures stack traces (`exc_info=True`)
- [x] Performance metrics logged (duration_ms in request logs)

---

## 🛠️ Troubleshooting

### Logs not appearing in JSON?

Check if logging is configured:
```python
# Must be called at startup
configure_logging("my-service", "INFO")
```

### Trace ID not propagating?

Ensure middleware is setup:
```python
from common.middleware import setup_logging_middleware
setup_logging_middleware(app)
```

And HTTP calls include header:
```python
headers = {"X-Request-ID": trace_id}
```

### Too many logs (spam)?

Increase log level:
```bash
LOG_LEVEL=WARNING docker-compose up
```

Or add paths to `EXCLUDE_PATHS` in `middleware.py`.

---

## 📚 Resources

- [structlog documentation](https://www.structlog.org/)
- [FastAPI middleware docs](https://fastapi.tiangolo.com/tutorial/middleware/)
- Story 0.4 implementation: `packages/common/logging.py`, `packages/common/middleware.py`

---

