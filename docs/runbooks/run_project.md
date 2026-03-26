# Run Full Project Locally (Environment + RAG + Agent + UI)

This runbook captures the exact flow used to bring the full project up locally and test ReAct + recommendation generation end-to-end.

## 1. Prerequisites

- Docker Desktop running
- `uv` installed
- AWS CLI installed and configured

```bash
docker login
```

## 2. Start from Repo Root

Run from the repository root:

```bash
pwd
```

Expected: path ending with `BeliefCraft`.

## 3. Configure Environment Variables

Populate service env files from examples (do this once).

```bash
cp .env.example .env
cp services/agent-service/.env.example services/agent-service/.env
cp services/environment-api/.env.example services/environment-api/.env
cp services/rag-service/.env.example services/rag-service/.env
cp services/ui/.env.example services/ui/.env
cp packages/database.env.example packages/database/.env
```

Then fill the values in the copied `.env` files.
The packages/database/.env is pinned in discord chat.

### AWS Credentials Setup (Required for Bedrock & Weaviate)

**Docker mode:** Containers cannot access `~/.aws` on the host. AWS credentials must be injected as environment variables via Docker Compose.

1. **Configure your local AWS CLI** to save your credentials to your machine:

   ```bash
   aws configure
   ```

   _Provide your `AWS Access Key ID`, `AWS Secret Access Key`, and Default region (e.g., `us-east-1`) when prompted._

2. **Load credentials into your active terminal session**:

   Linux/macOS:

   ```bash
   . scripts/aws-env.sh
   ```

   PowerShell:

   ```powershell
   . .\scripts\aws-env.ps1
   ```

**Important**: You must run the load script in the exact same terminal window where you run `docker compose up`. If you open a new terminal tab, run the script again.

## 4. Choose Run Mode

### Option A: Full Docker (default)

All services run in containers. See next section for clean start.

### Option B: Local Python services + Docker infrastructure

Run only infrastructure in Docker and Python services natively. This allows `AWS_PROFILE` usage, faster iteration, and direct debugger access.

**Start infrastructure only:**

```bash
docker compose up -d weaviate redis
```

**Run each Python service** (each in its own terminal, from repo root):

```bash
# Environment API
uv run uvicorn environment_api.main:app --host 0.0.0.0 --port 8000 --reload

# RAG Service
uv run uvicorn rag_service.main:app --host 0.0.0.0 --port 8001 --reload

# Agent Service
ENVIRONMENT_API_URL=http://localhost:8000 \
RAG_API_URL=http://localhost:8001 \
REDIS_URL=redis://localhost:6379 \
uv run uvicorn app.main:app --host 0.0.0.0 --port 8003 --reload
```

## 5. Clean Start — Docker (Recommended)

```bash
docker compose down -v --remove-orphans
docker compose up --build --remove-orphans
```

What this does:

- Removes old containers, network, and volumes (`down -v`)
- Rebuilds images (`--build`)
- Removes stale/orphan containers (`--remove-orphans`)

### Data persistence: Weaviate

Weaviate uses a **bind mount** (`./.weaviate_data:/var/lib/weaviate`).

| Command                     | Weaviate data |
| :-------------------------- | :------------ |
| `docker compose down`       | Kept          |
| `docker compose down -v`    | Kept          |
| `docker compose up --build` | Intact        |
| `rm -rf .weaviate_data`     | **Deleted**   |

`docker compose down -v` only removes **named volumes** — it does not touch host directory bind mounts. Your `.weaviate_data/` and ingested chunks survive any Docker restart.

**Restarting after code changes**:

```bash
docker compose up --build --remove-orphans
```

## 6. Confirm Services Are Healthy

In another terminal:

```bash
curl -s http://localhost:8000/health
curl -s http://localhost:8001/health
curl -s http://localhost:8003/api/v1/health
curl -s 'http://localhost:8003/api/v1/tools?category=rag'
```

## 7. Ingest Book Chunks into Weaviate

If your chunk JSON is at the repo root, run:

```bash
PYTHONPATH=services/rag-service/src \
uv run services/rag-service/src/rag_scripts/embed_chunks.py \
"./ULTIMATE_BOOK_DATA_25_03_translated.json" \
--recreate
```

Important:

- This command reads local JSON and inserts records into Weaviate over exposed ports.
- Data is persisted in `.weaviate_data`.

### Alternative: Restore Weaviate from shared backup

1. Place backup directory under:

   ```bash
   ./.weaviate_backups/backup_for_sharing
   ```

2. Ensure Weaviate is running:

   ```bash
   docker compose up weaviate
   ```

3. Run restore script:
   ```bash
   PYTHONPATH=services/rag-service/src \
   uv run services/rag-service/src/scripts/restore_weaviate_backup.py
   ```

## 8. Smoke Test Agent Analyze Endpoint

```bash
curl -s -X POST http://localhost:8003/api/v1/agent/analyze \
  -H 'Content-Type: application/json' \
  -d '{
    "query":"Analyze potential delay risks for all purchase orders currently assigned to the destination warehouse '\''WH-NA-EAST-01'\'' and expected in the next 48 hours.",
    "max_iterations": 8,
    "context": {}
  }'
```

Check response fields:

- `status` (`completed` / `partial`)
- `task`, `analysis`
- `recommendations` (non-empty)
- `tools_used`

## 9. Useful Additional Test Queries

1. `Analyze inventory discrepancy risk for fast-moving SKUs and propose immediate containment steps.`
2. `Recommend a replenishment policy under uncertain demand and lead time; include algorithm, formula, and Python code.`
3. `For service level 95% and volatile demand, how should reorder points and safety stock be set?`
4. `Find a warehouse decision-making algorithm from the knowledge base and provide executable Python snippet with comments.`

## 10. Operational Logs (During Debugging)

```bash
docker compose logs -f agent-service rag-service environment-api
```

Targeted logs:

```bash
docker compose logs rag-service --tail=200
docker compose logs agent-service --tail=200
```

## 11. Common Issues Seen During Setup

### Docker image pull / TLS timeout

Symptoms: pull fails with TLS handshake timeout.
Actions:

- `docker login`
- retry `docker compose up --build --remove-orphans`
