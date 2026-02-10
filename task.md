### **User Story**

**As a** backend developer  
**I want** a FastAPI project structure with health checks and basic endpoints  
**So that** I have a solid foundation to build the agent service

---

### **Acceptance Criteria**

- [ ] FastAPI application runs on port 8003 (configurable via env)
- [ ] Project follows shared monorepo structure from Epic 0
- [ ] Health check endpoint returns service status + LLM connectivity
- [ ] OpenAPI documentation accessible at `/docs`
- [ ] CORS configured for UI integration
- [ ] Environment variables managed via `.env` file
- [ ] Dockerfile builds successfully with multi-stage build
- [ ] Service starts via docker-compose with dependencies (Redis)
- [ ] Structured logging configured (from Epic 0 standards)
- [ ] Basic error handling middleware (returns JSON errors)

---

### **Technical Tasks**

#### **Task 1: Initialize FastAPI Project**
```bash
services/agent-service/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI app initialization
│   ├── config.py            # Settings (Pydantic BaseSettings)
│   ├── api/
│   │   ├── __init__.py
│   │   ├── v1/
│   │   │   ├── __init__.py
│   │   │   └── routes/
│   │   │       ├── health.py
│   │   │       ├── agent.py (placeholder)
│   │   │       └── tools.py (placeholder)
│   ├── core/
│   │   ├── __init__.py
│   │   ├── logging.py       # Import from common package
│   │   └── exceptions.py    # Custom exceptions
│   ├── models/              # Pydantic schemas
│   │   ├── __init__.py
│   │   └── requests.py
│   │   └── responses.py
│   └── services/            # Business logic (to be added)
├── tests/
│   ├── __init__.py
│   └── test_health.py
├── Dockerfile
├── requirements.txt
├── pyproject.toml
└── .env.example
```

**Subtasks:**
- [x] Create directory structure
- [x] Initialize Poetry/pip project with dependencies:
  ```
  fastapi==0.104.1
  uvicorn[standard]==0.24.0
  pydantic==2.5.0
  pydantic-settings==2.1.0
  redis==5.0.1
  httpx==0.25.0
  structlog==23.2.0
  python-dotenv==1.0.0
  ```
- [x] Create `main.py` with FastAPI app initialization
- [x] Configure CORS middleware

---

#### **Task 2: Implement Configuration Management**

**File:** `app/config.py`

```python
from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    # Service config
    SERVICE_NAME: str = "agent-service"
    SERVICE_VERSION: str = "0.1.0"
    API_V1_PREFIX: str = "/api/v1"
    HOST: str = "0.0.0.0"
    PORT: int = 8003
    
    # External services
    ENVIRONMENT_API_URL: str
    RAG_API_URL: str
    
    # LLM config
    OPENAI_API_KEY: str
    OPENAI_MODEL: str = "gpt-4-turbo-preview"
    OPENAI_TEMPERATURE: float = 0.0
    OPENAI_MAX_TOKENS: int = 4000
    
    # Redis cache
    REDIS_URL: str = "redis://localhost:6379"
    CACHE_TTL_SECONDS: int = 3600
    
    # Agent config
    MAX_ITERATIONS: int = 10
    TOOL_TIMEOUT_SECONDS: int = 30
    
    # Logging
    LOG_LEVEL: str = "INFO"
    
    class Config:
        env_file = ".env"
        case_sensitive = True

@lru_cache()
def get_settings() -> Settings:
    return Settings()
```

**Subtasks:**
- [ ] Create `.env.example` with all required variables
- [ ] Add validation for required fields
- [ ] Test settings loading

---

#### **Task 3: Implement Health Check Endpoint**

**File:** `app/api/v1/routes/health.py`

```python
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from app.config import Settings, get_settings
import httpx
import redis
from datetime import datetime

router = APIRouter()

class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    timestamp: str
    dependencies: dict

@router.get("/health", response_model=HealthResponse)
async def health_check(settings: Settings = Depends(get_settings)):
    """
    Health check endpoint - verifies service and dependencies
    """
    dependencies = {
        "environment_api": "unknown",
        "rag_api": "unknown",
        "redis": "unknown",
        "openai": "unknown"
    }
    
    # Check Environment API
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{settings.ENVIRONMENT_API_URL}/health")
            dependencies["environment_api"] = "healthy" if resp.status_code == 200 else "unhealthy"
    except Exception as e:
        dependencies["environment_api"] = f"error: {str(e)}"
    
    # Check RAG API
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{settings.RAG_API_URL}/health")
            dependencies["rag_api"] = "healthy" if resp.status_code == 200 else "unhealthy"
    except Exception as e:
        dependencies["rag_api"] = f"error: {str(e)}"
    
    # Check Redis
    try:
        r = redis.from_url(settings.REDIS_URL, decode_responses=True)
        r.ping()
        dependencies["redis"] = "healthy"
    except Exception as e:
        dependencies["redis"] = f"error: {str(e)}"
    
    # Check OpenAI (simple key validation)
    dependencies["openai"] = "configured" if settings.OPENAI_API_KEY else "missing_key"
    
    # Overall status
    all_healthy = all(
        status in ["healthy", "configured"] 
        for status in dependencies.values()
    )
    
    return HealthResponse(
        status="healthy" if all_healthy else "degraded",
        service=settings.SERVICE_NAME,
        version=settings.SERVICE_VERSION,
        timestamp=datetime.utcnow().isoformat(),
        dependencies=dependencies
    )
```

**Subtasks:**
- [ ] Implement health check logic
- [ ] Add timeout handling for external services
- [ ] Write unit tests with mocked dependencies

---

#### **Task 4: Setup Structured Logging**

**File:** `app/core/logging.py`

```python
import structlog
import logging
from app.config import get_settings

def configure_logging():
    settings = get_settings()
    
    logging.basicConfig(
        format="%(message)s",
        level=getattr(logging, settings.LOG_LEVEL),
    )
    
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer()
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    
    return structlog.get_logger()
```

**File:** `app/main.py`

```python
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.config import get_settings
from app.core.logging import configure_logging
from app.core.exceptions import AgentServiceException
from app.api.v1.routes import health
import structlog
import time
import uuid

# Configure logging
logger = configure_logging()

# Initialize FastAPI
settings = get_settings()
app = FastAPI(
    title="BeliefCraft Agent Service",
    description="ReAct agent for warehouse decision support",
    version=settings.SERVICE_VERSION,
    docs_url=f"{settings.API_V1_PREFIX}/docs",
    openapi_url=f"{settings.API_V1_PREFIX}/openapi.json"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure properly for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request ID middleware
@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(request_id=request_id)
    
    start_time = time.time()
    response = await call_next(request)
    duration_ms = (time.time() - start_time) * 1000
    
    logger.info(
        "request_completed",
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        duration_ms=round(duration_ms, 2)
    )
    
    response.headers["X-Request-ID"] = request_id
    return response

# Exception handler
@app.exception_handler(AgentServiceException)
async def agent_exception_handler(request: Request, exc: AgentServiceException):
    logger.error(
        "agent_error",
        error_type=type(exc).__name__,
        error_message=str(exc),
        request_id=request.state.request_id
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.error_code,
            "message": str(exc),
            "request_id": request.state.request_id
        }
    )

# Include routers
app.include_router(
    health.router,
    prefix=settings.API_V1_PREFIX,
    tags=["health"]
)

@app.on_event("startup")
async def startup_event():
    logger.info("agent_service_starting", version=settings.SERVICE_VERSION)

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("agent_service_stopping")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=True
    )
```

**Subtasks:**
- [ ] Configure structlog with JSON output
- [ ] Add request ID middleware
- [ ] Add request timing middleware
- [ ] Test logging output format

---

#### **Task 5: Create Dockerfile and Docker Compose Integration**

**File:** `services/agent-service/Dockerfile`

```dockerfile
FROM python:3.11-slim as base

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY app/ ./app/

# Create non-root user
RUN useradd -m -u 1000 agent && chown -R agent:agent /app
USER agent

EXPOSE 8003

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8003"]
```

**File:** `docker-compose.yml` (add agent service)

```yaml
services:
  # ... existing services ...
  
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 5
  
  agent-service:
    build:
      context: ./services/agent-service
      dockerfile: Dockerfile
    ports:
      - "8003:8003"
    environment:
      - ENVIRONMENT_API_URL=http://environment-api:8001/api/v1
      - RAG_API_URL=http://rag-service:8002/api/v1
      - REDIS_URL=redis://redis:6379
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - LOG_LEVEL=INFO
    depends_on:
      - redis
      - environment-api
      - rag-service
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8003/api/v1/health"]
      interval: 10s
      timeout: 5s
      retries: 3
```

**Subtasks:**
- [ ] Write Dockerfile with multi-stage build
- [ ] Add agent-service to docker-compose.yml
- [ ] Test container build
- [ ] Verify health check works in container

---

#### **Task 6: Write Tests**

**File:** `tests/test_health.py`

```python
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock
from app.main import app

client = TestClient(app)

def test_health_endpoint_exists():
    """Health endpoint should be accessible"""
    response = client.get("/api/v1/health")
    assert response.status_code == 200

@patch("app.api.v1.routes.health.httpx.AsyncClient")
@patch("app.api.v1.routes.health.redis.from_url")
def test_health_all_services_healthy(mock_redis, mock_httpx):
    """Health check should return healthy when all deps are up"""
    # Mock external API calls
    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_httpx.return_value.__aenter__.return_value.get.return_value = mock_response
    
    # Mock Redis
    mock_redis.return_value.ping.return_value = True
    
    response = client.get("/api/v1/health")
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "agent-service"
    assert "dependencies" in data

def test_health_includes_version():
    """Health check should include service version"""
    response = client.get("/api/v1/health")
    data = response.json()
    assert "version" in data
    assert "timestamp" in data
```

**Subtasks:**
- [ ] Write unit tests for health endpoint
- [ ] Test with mocked dependencies (healthy scenario)
- [ ] Test with failed dependencies (degraded scenario)
- [ ] Verify response schema

---

#### **Task 7: Documentation**

**File:** `services/agent-service/README.md`

```markdown
# Agent Service

ReAct-based warehouse decision advisor.

## Setup

### Local Development

```bash
cd services/agent-service
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your API keys
uvicorn app.main:app --reload --port 8003
```

### Docker

```bash
docker-compose up agent-service
```

## API Endpoints

- `GET /api/v1/health` - Health check
- `POST /api/v1/agent/analyze` - Analyze warehouse query (TODO)
- `GET /api/v1/docs` - OpenAPI documentation

## Configuration

See `.env.example` for all environment variables.

## Testing

```bash
pytest tests/ -v
```

**Subtasks:**
- [ ] Write README with setup instructions
- [ ] Document environment variables
- [ ] Add API endpoint documentation (OpenAPI auto-generated)

---

### **Definition of Done**

- [ ] FastAPI service runs locally on port 8003
- [ ] Health check endpoint returns JSON with dependency status
- [ ] Service starts in Docker with docker-compose
- [ ] Structured logging outputs JSON format
- [ ] All dependencies checked in health endpoint (Env API, RAG API, Redis, OpenAI)
- [ ] Unit tests pass (>80% coverage for health endpoint)
- [ ] OpenAPI docs accessible at `/api/v1/docs`
- [ ] Request ID added to all responses via header
- [ ] Error handling middleware returns proper JSON errors
- [ ] README documentation complete

---

### **Dependencies**

**Requires:**
- Epic 0 completed (project structure, Docker setup)
- Redis container available in docker-compose
- Environment API and RAG API endpoints defined (can use mocks initially)

**Blocks:**
- Story 3.2 (ReAct loop needs base API)
- Story 3.3 (Tools need service infrastructure)

---

### **Notes for Developers**

- Use `httpx` for async HTTP calls (not `requests`)
- All external API calls should have timeouts (default: 30s)
- Redis client should use connection pooling (default in redis-py)
- OpenAI API key should never be logged or returned in responses
- Health check should not fail entire service if one dependency is down (return "degraded" status)