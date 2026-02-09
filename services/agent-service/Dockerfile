FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

COPY pyproject.toml uv.lock ./

RUN pip install --no-cache-dir uv \
  && uv sync --frozen --system

COPY src ./src

EXPOSE 8002

CMD ["sh", "-c", "uvicorn agent_service.main:app --host 0.0.0.0 --port ${PORT:-8002}"]
