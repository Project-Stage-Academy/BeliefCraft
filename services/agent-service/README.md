# Agent Service

ReAct-based warehouse decision advisor powered by Claude Sonnet 4.5.

## Overview

The Agent Service implements a ReAct (Reasoning and Acting) agent that processes warehouse queries, interacts with external APIs, and provides intelligent decision support using Claude Sonnet 4.5.

## Features

- 🤖 ReAct agent with Claude Sonnet 4.5
- 🔄 Health check with dependency monitoring
- 📊 Structured JSON logging
- 🔒 Request ID tracking
- 🐳 Docker support
- 📝 OpenAPI documentation

## Setup

### Local Development

1. **Install dependencies:**
   ```bash
   cd services/agent-service
   pip install uv
   uv sync
   ```

2. **Configure environment:**
   ```bash
   cp .env.example .env
   # Edit .env with your Anthropic API key
   ```

3. **Run the service:**
   ```bash
   uv run uvicorn app.main:app --reload --port 8003
   ```

4. **Access the service:**
   - Root: http://localhost:8003/
   - Health: http://localhost:8003/api/v1/health
   - Docs: http://localhost:8003/api/v1/docs

### Docker

```bash
# From project root
docker-compose up agent-service
```

## API Endpoints

### Root
```
GET /
```
Returns service information and available endpoints

### Health Check
```
GET /api/v1/health
```
Returns service status and dependency health:
- Environment API connectivity
- RAG API connectivity  
- Redis connectivity
- Anthropic API configuration

### Agent Query (Coming Soon)
```
POST /api/v1/agent/analyze
```

### Documentation
```
GET /api/v1/docs
```
Interactive OpenAPI documentation (Swagger UI)

## Configuration

All configuration is managed via environment variables. See `.env.example` for available options.

### Required Variables

- `ANTHROPIC_API_KEY` - Your Anthropic API key
- `ENVIRONMENT_API_URL` - Environment API endpoint
- `RAG_API_URL` - RAG service endpoint
- `REDIS_URL` - Redis connection URL

### Optional Variables

- `ANTHROPIC_MODEL` - Claude model (default: claude-sonnet-4.5)
- `MAX_ITERATIONS` - Maximum ReAct iterations (default: 10)
- `LOG_LEVEL` - Logging level (default: INFO)

## Testing

```bash
# Run all tests
uv run pytest tests/ -v

# Run with coverage
uv run pytest tests/ --cov=app --cov-report=html
```

## Architecture

```
app/
├── main.py              # FastAPI application
├── config.py            # Configuration management
├── api/
│   └── v1/
│       └── routes/
│           ├── health.py    # Health check endpoint
│           ├── agent.py     # Agent endpoints (TODO)
│           └── tools.py     # Tool endpoints (TODO)
├── core/
│   ├── logging.py       # Structured logging
│   └── exceptions.py    # Custom exceptions
├── models/              # Pydantic schemas
│   ├── requests.py
│   └── responses.py
└── services/            # Business logic (TODO)
```

## Development

### Adding New Endpoints

1. Create route in `app/api/v1/routes/`
2. Define request/response models in `app/models/`
3. Include router in `app/main.py`

### Logging

Use structured logging throughout:

```python
from app.core.logging import configure_logging

logger = configure_logging()
logger.info("event_name", key1="value1", key2="value2")
```

### Error Handling

Raise custom exceptions for proper error responses:

```python
from app.core.exceptions import AgentServiceException

raise AgentServiceException(
    message="Error description",
    status_code=500,
    error_code="ERROR_CODE"
)
```

## Dependencies

- FastAPI - Web framework
- Uvicorn - ASGI server
- Pydantic - Data validation
- Anthropic - Claude API client
- Redis - Caching
- Structlog - Structured logging
- HTTPX - Async HTTP client

## License

Internal use only.
