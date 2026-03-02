# Vector Database Workflow Tutorial

This guide explains how to manage the Weaviate vector database in BeliefCraft, including embedding data chunks, creating backups for sharing, and restoring from shared backups.

## Prerequisites

1. **Docker Compose:** Ensure you have Docker installed and running.
2. **AWS Credentials:** You need AWS credentials with access to Amazon Bedrock for embeddings.
3. **uv:** Python package manager used for running scripts.
4. **AWS CLI:** Configured on your machine.

---

## 1. Setup Environment

### Load AWS Credentials

To use Bedrock embeddings, you must load your AWS credentials into your environment variables.
Run these scripts to load them from AWS CLI configuration:

**On Linux/macOS:**
```bash
. scripts/aws-env.sh
```

**On Windows (PowerShell):**
```powershell
. .\scripts\aws-env.ps1
```

### Start Weaviate

Start the Weaviate service using Docker Compose:

```bash
docker compose up weaviate -d
```

---

## 2. Embedding Chunks into Database

Use the `embed_chunks.py` script to process a JSON file containing document chunks and store them in Weaviate.

```bash
PYTHONPATH=services/rag-service/src uv run services/rag-service/src/scripts/embed_chunks.py path/to/your/chunks.json
```

**Options:**
- `--recreate`: (Optional) Use this flag to delete the existing collection and start fresh.

---

## 3. Sharing the Database (Backup)

To share your local data with other developers, create a filesystem backup.

### Create Backup

Run the following script to generate a backup named `backup_for_sharing`:

```bash
PYTHONPATH=services/rag-service/src uv run services/rag-service/src/scripts/create_weaviate_backup.py
```

The backup will be stored in the `./.weaviate_backups/backup_for_sharing` directory.

### Share with Others

You can compress and share the contents of `./.weaviate_backups/backup_for_sharing` with other developers.

---

## 4. Loading from Shared Backup

If you received a backup from another developer:

1. Place the backup folder into your `./.weaviate_backups/` directory.
2. Ensure Weaviate is running (`docker compose up weaviate -d`).
3. Run the restore script:

```bash
PYTHONPATH=services/rag-service/src uv run services/rag-service/src/scripts/restore_weaviate_backup.py
```
