FROM python:3.11-slim as builder

WORKDIR /app/services/agent-service

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Set Python environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install uv
RUN pip install --no-cache-dir uv

# Copy dependency files
COPY services/agent-service/pyproject.toml services/agent-service/uv.lock ./
COPY packages/common /app/packages/common

# Install dependencies with uv
RUN uv sync --frozen --no-dev


FROM python:3.11-slim as runtime

WORKDIR /app/services/agent-service

# Set Python environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app:/app/packages:/app/services/agent-service

# Copy virtual environment and app code
COPY --from=builder /app/services/agent-service/.venv /app/services/agent-service/.venv
COPY packages/common /app/packages/common
COPY services/agent-service/app ./app

# Create non-root user
RUN useradd -m -u 1000 agent && chown -R agent:agent /app
USER agent

EXPOSE 8003

CMD ["/app/services/agent-service/.venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8003"]
