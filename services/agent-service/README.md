# Agent Service

ReAct-based warehouse decision advisor for the BeliefCraft platform.

## Quick Start

### Local Development

```bash
cd services/agent-service

# Install dependencies
pip install uv
uv sync

# Configure environment
cp .env.example .env
# Edit .env with your API keys

# Run the service
uv run uvicorn app.main:app --reload --port 8003
```

**Access:**
- API: http://localhost:8003
- Health: http://localhost:8003/api/v1/health
- Docs: http://localhost:8003/api/v1/docs

### Docker

```bash
# From project root
docker-compose up agent-service
```

## Essential Configuration

Create `.env` file with these **required** variables:

```bash
ENVIRONMENT_API_URL=http://localhost:8001/api/v1
RAG_API_URL=http://localhost:8001
ANTHROPIC_API_KEY=your_anthropic_api_key_here
```

### LangSmith Tracing (Optional)

[LangSmith](https://smith.langchain.com/) provides tracing, debugging, and evaluation for all LLM calls made by the agent.

**Setup:**

1. Create a free account at https://smith.langchain.com/ and obtain an API key.
2. Add the following variables to your `.env` file:

```bash
# Enable tracing
LANGCHAIN_TRACING_V2=true
# Your LangSmith API key
LANGCHAIN_API_KEY=ls__your_api_key_here
# Project name that will group traces in the dashboard
LANGCHAIN_PROJECT=beliefcraft-dev
```

3. Restart the service. On startup you will see `langsmith_tracing_enabled` in the logs.
4. Open https://smith.langchain.com/ and navigate to your project to inspect traces.

When `LANGCHAIN_TRACING_V2` is `false` or `LANGCHAIN_API_KEY` is unset, tracing is silently skipped and the service runs normally.

See [Configuration Guide](../../docs/agent-service/CONFIGURATION.md) for all options.

## API Endpoints

- **GET** `/api/v1/health` - Health check with dependency status
- **POST** `/api/v1/agent/analyze` - Agent query (planned; not implemented yet)
- **GET** `/api/v1/docs` - Interactive API documentation

See [API Documentation](../../docs/agent-service/API.md) for detailed endpoint specifications.

## Testing

```bash
# Run all tests
uv run pytest tests/ -v

# With coverage
uv run pytest tests/ --cov=app --cov-report=html
```

## Project Structure

```
services/agent-service/
 app/
    main.py              # FastAPI app initialization
    config.py            # Configuration management
    api/v1/routes/       # API endpoints
    core/                # Logging, exceptions
    models/              # Pydantic schemas
    services/            # Business logic
 tests/                   # Unit tests
 Dockerfile
 pyproject.toml
 .env.example
```

## Documentation

- **[API Documentation](../../docs/agent-service/API.md)** - Complete API reference
- **[Configuration Guide](../../docs/agent-service/CONFIGURATION.md)** - All configuration options
- **[Deployment Guide](../../docs/agent-service/DEPLOYMENT.md)** - Deployment instructions
- **[Architecture](../../docs/agent-service/ARCHITECTURE.md)** - Architecture and design

## Status

###  Completed

- FastAPI application with health checks
- Configuration management
- Structured JSON logging
- Request ID middleware
- Error handling middleware
- CORS configuration
- OpenAPI documentation
- Docker support
- Unit tests

###  In Progress

- ReAct agent implementation
- Agent query endpoint
- Tool system

## Support

For issues or questions:

1. Check the [documentation](../../docs/agent-service/)
2. Review API docs at `/api/v1/docs`
3. Check service logs
4. See [task.md](../../task.md) for requirements

## License

Internal use only - BeliefCraft Project
