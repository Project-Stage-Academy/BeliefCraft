FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/services/environment-api/src \
    PORT=8000

RUN pip install --no-cache-dir uv

COPY services/environment-api/pyproject.toml services/environment-api/uv.lock ./
RUN uv sync --frozen

COPY packages/common /app/packages/common
RUN uv pip install --python /app/.venv/bin/python -e /app/packages/common

COPY services/environment-api/src /app/services/environment-api/src
COPY services/environment-api/config /app/services/environment-api/config

EXPOSE 8000

CMD ["/app/.venv/bin/uvicorn", "main:app",  "--host", "0.0.0.0", "--port", "8000"]
