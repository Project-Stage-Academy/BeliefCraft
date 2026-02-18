FROM python:3.11-slim AS builder

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN pip install --no-cache-dir uv

COPY services/rag-service/pyproject.toml services/rag-service/uv.lock ./
COPY packages/common /app/packages/common
RUN uv sync --frozen --no-dev


FROM python:3.11-slim AS runtime

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    PORT=8001

COPY --from=builder /app/.venv /app/.venv
COPY packages/common /app/packages/common
COPY services/rag-service/src /app/src
COPY services/rag-service/config /app/config

EXPOSE 8001

CMD ["/app/.venv/bin/uvicorn", "rag_service.main:app", "--host", "0.0.0.0", "--port", "8001"]
