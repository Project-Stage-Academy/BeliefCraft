FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app:/app/services/environment-api \
    PORT=8000

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock /app/
COPY packages/common /app/packages/common
COPY packages/database /app/packages/database
COPY services/environment-api /app/services/environment-api

RUN uv sync --frozen --project services/environment-api

EXPOSE 8000

CMD ["uv", "run", "--frozen", "--project", "services/environment-api", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
