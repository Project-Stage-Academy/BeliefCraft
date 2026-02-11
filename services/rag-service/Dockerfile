FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    PORT=8001

RUN pip install --no-cache-dir uv

COPY services/rag-service/pyproject.toml services/rag-service/uv.lock ./
RUN uv sync --frozen

COPY packages/common /app/packages/common
RUN uv pip install --python /app/.venv/bin/python -e /app/packages/common

COPY services/rag-service/src /app/src
COPY services/rag-service/config /app/config

EXPOSE 8001

CMD ["uv", "run", "uvicorn", "rag_service.main:app", "--host", "0.0.0.0", "--port", "8001"]
