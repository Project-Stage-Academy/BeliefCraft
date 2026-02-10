FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    PORT=8000

COPY pyproject.toml uv.lock ./

RUN pip install --no-cache-dir uv \
  && uv sync --frozen --system

COPY src ./src

EXPOSE 8000

CMD ["uvicorn", "environment_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
