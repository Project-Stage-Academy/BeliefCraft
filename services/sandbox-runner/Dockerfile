# file: services/sandbox-runner/Dockerfile
FROM python:3.11-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Install docker client required by llm-sandbox
RUN apt-get update && apt-get install -y docker.io && rm -rf /var/lib/apt/lists/*

# Set the working directory to the root of the repo inside the container
WORKDIR /app

# 1. Copy the root workspace files and the common package
COPY pyproject.toml uv.lock ./
COPY packages/common/ packages/common/

# 2. Copy the sandbox-runner pyproject
COPY services/sandbox-runner/pyproject.toml services/sandbox-runner/

# 3. Install dependencies WITHOUT the code yet (caches the layer!)
RUN uv sync --frozen --no-install-project

# 4. NOW copy the application code using the correct path from the repo root
COPY services/sandbox-runner/app/ services/sandbox-runner/app/

# 5. Final sync to install the app code itself
RUN uv sync --frozen

# 6. Move into the service directory before starting the server
WORKDIR /app/services/sandbox-runner

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
