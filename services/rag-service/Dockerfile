FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

# Install uv
RUN pip install --no-cache-dir uv

# Copy dependency file
COPY pyproject.toml ./

# Install dependencies with uv
RUN uv pip install --system -e .

COPY src ./src

EXPOSE 8001

CMD ["sh", "-c", "uvicorn rag_service.main:app --host 0.0.0.0 --port ${PORT:-8001}"]
