FROM python:3.11-slim AS builder

WORKDIR /app

# Set Python environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install uv
RUN pip install --no-cache-dir uv

# Copy workspace files
COPY pyproject.toml uv.lock /app/
COPY packages/common /app/packages/common
COPY services/agent-service /app/services/agent-service

# Install dependencies with uv workspace
RUN uv sync --frozen --project services/agent-service


FROM python:3.11-slim AS runtime

WORKDIR /app

# Set Python environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app:/app/packages:/app/services/agent-service

# Copy virtual environment and app code
COPY --from=builder /app/.venv /app/.venv
COPY packages/common /app/packages/common
COPY services/agent-service/app /app/services/agent-service/app
COPY services/agent-service/config /app/services/agent-service/config

# Create non-root user
RUN useradd -m -u 1000 agent && chown -R agent:agent /app
USER agent

EXPOSE 8003

CMD ["/app/.venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8003", "--app-dir", "/app/services/agent-service"]
