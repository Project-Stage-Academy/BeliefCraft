FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    PORT=8000

# Install uv
RUN pip install --no-cache-dir uv

# Copy dependency file
COPY pyproject.toml ./

# Install dependencies with uv
RUN uv pip install --system -e .

COPY src ./src

EXPOSE 8000

CMD ["uvicorn", "environment_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
