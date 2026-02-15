FROM python:3.11-slim AS builder

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN pip install --no-cache-dir uv

COPY services/environment-api/pyproject.toml services/environment-api/uv.lock ./
COPY packages/common /app/packages/common
RUN uv sync --frozen --no-dev


FROM python:3.11-slim AS runtime

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/services/environment-api/src:/app/packages/common \
    PORT=8000

COPY --from=builder /app/.venv /app/.venv
COPY packages/common /app/packages/common
COPY services/environment-api/src /app/services/environment-api/src
COPY services/environment-api/config /app/services/environment-api/config

EXPOSE 8000

CMD ["/app/.venv/bin/uvicorn", "main:app",  "--host", "0.0.0.0", "--port", "8000"]
