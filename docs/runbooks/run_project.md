# Run Full Project Locally (Environment + RAG + Agent + UI)

This runbook captures the exact flow used to bring the full project up locally and test ReAct + recommendation generation end-to-end.

## 1. Prerequisites

- Docker Desktop running
- `uv` installed
- AWS credentials available for Bedrock access

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

Quick copy command

```bash
cp .env.example .env
cp services/agent-service/.env.example services/agent-service/.env
cp services/environment-api/.env.example services/environment-api/.env
cp services/rag-service/.env.example services/rag-service/.env
cp services/ui/.env.example services/ui/.env
```

Then fill the values in:

- `services/environment-api/.env`
- `services/rag-service/.env`
- `services/agent-service/.env`
- `services/ui/.env` (if needed)
- root `.env` for Docker Compose variables

Notes:

- Environment API can use local Postgres (compose) or external Supabase/Postgres.
- Docker compose may still start local Postgres service for other project flows.

### AWS auth note (profile vs access keys)

- `agent-service` env supports both:
  - `AWS_PROFILE` in `services/agent-service/.env`
  - or `AWS_ACCESS_KEY_ID` + `AWS_SECRET_ACCESS_KEY`
- If using `AWS_PROFILE`, ensure your local `~/.aws` has that profile (compose mounts `~/.aws` into `agent-service`).
- `rag-service` Weaviate vectorizer is configured via compose env from root `.env`:
  - `AWS_ACCESS_KEY_ID`
  - `AWS_SECRET_ACCESS_KEY`
    Profile-based auth is not used by Weaviate module in this setup.

### Supabase credentials note

For `environment-api`, put DB config in `services/environment-api/.env`:

- Preferred: set `DATABASE_URL` directly.
- Fallback supported by database package: set
  - `SUPABASE_USER`
  - `SUPABASE_PASSWORD`
  - `SUPABASE_HOST`
  - `SUPABASE_PORT`
  - `SUPABASE_DB`

## 4. Clean Start (Recommended)

```bash
docker compose down -v --remove-orphans
docker compose up --build --remove-orphans
```

What this does:

- Removes old containers, network, and volumes (`down -v`)
- Rebuilds images (`--build`)
- Removes stale/orphan containers (`--remove-orphans`)

## 5. Confirm Services Are Healthy

In another terminal:

```bash
curl -s http://localhost:8000/health
curl -s http://localhost:8001/health
curl -s http://localhost:8003/api/v1/health
curl -s 'http://localhost:8003/api/v1/tools?category=rag'
```

Expected:

- Environment API healthy
- RAG service healthy
- Agent service healthy
- RAG tools listed:
  - `search_knowledge_base`
  - `expand_graph_by_ids`
  - `get_entity_by_number`

## 6. Ingest Book Chunks into Weaviate

If your chunk JSON is at repo root, run:

```bash
PYTHONPATH=services/rag-service/src \
uv run services/rag-service/src/scripts/embed_chunks.py \
"./ULTIMATE_FINAL_BOOK(with correct formulas and translated).json" \
--recreate #download this json from google drive (links in discord)
```

Without full re-create (incremental insert), omit `--recreate`.

Important:

- This command does **not** copy JSON into containers.
- It reads local JSON and inserts records into Weaviate over its exposed ports.
- Data is persisted in Docker volume/path (`.weaviate_data` via compose mount).

## 7. Import Weaviate Data from a Shared Backup

If another developer has shared a Weaviate backup with you (e.g. via Google Drive or a shared archive), follow these steps instead of running the full embedding pipeline.

### 1. Place the backup

Unpack the received archive into the `.weaviate_backups/` directory at the repo root so the folder structure looks like:

```
.weaviate_backups/
└── backup_for_sharing/
    └── ...
```

### 2. Start Weaviate

Ensure Weaviate is running (if the full stack is not already up):

```bash
docker compose up weaviate -d
```

### 3. Restore

```bash
PYTHONPATH=services/rag-service/src \
uv run services/rag-service/src/scripts/restore_weaviate_backup.py
```

The script restores the `backup_for_sharing` backup into your local Weaviate instance.
Data is persisted in the Docker volume (`.weaviate_data` via compose mount).

> For full details on the backup/restore workflow, see [docs/rag-service/vector-db-workflow.md](../rag-service/vector-db-workflow.md).

## 8. Smoke Test Agent Analyze Endpoint

```bash
curl -s -X POST http://localhost:8003/api/v1/agent/analyze \
  -H 'Content-Type: application/json' \
  -d '{
    "query":"Which orders are at risk in the next 48 hours? Give prioritized actions.",
    "max_iterations": 8,
    "context": {}
  }'
```

Check response fields:

- `status` (`completed` / `partial`)
- `task`, `analysis`
- `recommendations` (non-empty)
- `tools_used`
- optional: `formulas`, `code_snippets`, `citations`, `warnings`

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
docker compose logs db-migrate --tail=200
docker compose logs postgres --tail=200
docker compose logs rag-service --tail=200
docker compose logs agent-service --tail=200
```

## 11. Common Issues Seen During Setup

### A) Docker image pull / TLS timeout

Symptoms:

- pull fails with TLS handshake timeout

Actions:

- `docker login`
- retry `docker compose up --build --remove-orphans`

### B) Postgres init/migration problems

Symptoms:

- `db-migrate` fails
- auth errors or script execution errors

Actions:

- run clean start (`docker compose down -v --remove-orphans`)
- restart compose from scratch
- inspect migration and postgres logs
