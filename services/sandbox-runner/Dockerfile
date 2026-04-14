FROM python:3.11-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# 1. Copy the root workspace files and the common package
COPY pyproject.toml uv.lock ./
COPY packages/common/ packages/common/

# 2. Copy the pyproject.toml of ALL Python workspace members so the lockfile validates
COPY services/agent-service/pyproject.toml services/agent-service/
COPY services/environment-api/pyproject.toml services/environment-api/
COPY services/rag-service/pyproject.toml services/rag-service/
COPY services/sandbox-runner/pyproject.toml services/sandbox-runner/

# 3. Sync ONLY the sandbox-runner dependencies (--no-dev keeps the image lean)
RUN uv sync --package beliefcraft-sandbox-runner --frozen --no-install-project --no-dev

# 4. NOW copy the actual application code for the runner
COPY services/sandbox-runner/app/ services/sandbox-runner/app/

# 5. Final sync to install the app code itself
RUN uv sync --package beliefcraft-sandbox-runner --frozen --no-dev

WORKDIR /app/services/sandbox-runner

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
