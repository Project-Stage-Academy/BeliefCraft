FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    PORT=8002

RUN pip install --no-cache-dir uv

COPY services/agent-service/pyproject.toml services/agent-service/uv.lock ./
RUN uv sync --frozen

COPY packages/common /app/packages/common
RUN uv pip install --python /app/.venv/bin/python -e /app/packages/common

COPY services/agent-service/src /app/src
COPY services/agent-service/config /app/config

EXPOSE 8002

CMD ["uv", "run", "uvicorn", "agent_service.main:app", "--host", "0.0.0.0", "--port", "8002"]
