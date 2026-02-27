# Local Development Setup

## Overview
This guide matches the current repository tooling (`Makefile`, `docker-compose.yml`, `.env.example` files).

## Prerequisites
- Docker + Docker Compose
- Python `>=3.11`
- `uv`
- Node.js + npm

## Step 1: Prepare Environment Files
From repo root:
```bash
cp .env.example .env
cp services/environment-api/.env.example services/environment-api/.env
cp services/rag-service/.env.example services/rag-service/.env
cp services/agent-service/.env.example services/agent-service/.env
cp services/ui/.env.example services/ui/.env
```

## Step 2: Install Dependencies
```bash
make setup
```

## Step 3: Start the Stack
```bash
make dev
```

This starts:
- `postgres` (`${POSTGRES_PORT}:5432`)
- `qdrant` (`${QDRANT_PORT}:6333`)
- `redis` (`${REDIS_PORT}:6379`)
- `environment-api` (`8000`)
- `rag-service` (`8001`)
- `agent-service` (`8003`)
- `ui` (`3000`)

## Step 4: Verify Health
- `http://localhost:8000/health`
- `http://localhost:8001/health`
- `http://localhost:8003/api/v1/health`
- `http://localhost:3000/health`

Optional script (PowerShell):
```powershell
powershell -ExecutionPolicy Bypass -File infrastructure/scripts/health/check-services.ps1
```

## Useful Commands
- Tail logs: `make logs`
- List containers: `make ps`
- Stop stack: `make down`
- Clean volumes: `make clean`

## Initialize/Refresh Simulation Data
On first startup, initialize domain tables and synthetic data:
```bash
cd services/environment-api
uv run python -m environment_api.data_generator.generate_seed_data
```

Notes:
- This step is required for meaningful smart-query responses on a fresh local database.
- The compose `db-migrate` job does not populate the environment simulation dataset.
