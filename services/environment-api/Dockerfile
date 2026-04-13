FROM python:3.11-slim AS builder

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock /app/
COPY packages/common /app/packages/common
COPY packages/database /app/packages/database
COPY services/environment-api /app/services/environment-api

RUN uv sync --frozen --project services/environment-api

FROM python:3.11-slim AS runtime

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app:/app/services/environment-api \
    PORT=8000

COPY --from=builder /app/.venv /app/.venv
COPY packages/common /app/packages/common
COPY packages/database /app/packages/database
COPY services/environment-api/src /app/services/environment-api/src
COPY services/environment-api/config /app/services/environment-api/config

EXPOSE 8000

CMD ["uv", "run", "--frozen", "--project", "services/environment-api", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
