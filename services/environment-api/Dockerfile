FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

COPY pyproject.toml requirements.txt ./

RUN pip install --no-cache-dir uv \
  && uv pip install --system -r requirements.txt

COPY src ./src

EXPOSE 8000

CMD ["sh", "-c", "uvicorn environment_api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
