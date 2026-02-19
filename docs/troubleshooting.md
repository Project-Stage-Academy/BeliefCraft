# Troubleshooting

## Docker Compose fails because `.env` files are missing

Create env files from examples before running `make dev`:

```powershell
copy .env.example .env
copy services\environment-api\.env.example services\environment-api\.env
copy services\rag-service\.env.example services\rag-service\.env
copy services\agent-service\.env.example services\agent-service\.env
copy services\ui\.env.example services\ui\.env
```

## PostgreSQL is up but services still cannot connect

1. Wait until `db-migrate` completes.
2. Inspect migration logs:

```powershell
docker compose logs db-migrate --tail=200
```

3. Verify PostgreSQL health:

```powershell
docker compose ps
```

## Health checks return non-200

Run the repository health script:

```powershell
powershell -ExecutionPolicy Bypass -File infrastructure/scripts/health/check-services.ps1
```

Then inspect service logs:

```powershell
docker compose logs environment-api rag-service agent-service ui --tail=200
```

## Hot reload does not reflect code changes

1. Ensure services were started with `make dev`.
2. Confirm bind mounts are active:

```powershell
docker compose exec environment-api ls /app/services/environment-api/src
```

3. Recreate containers if needed:

```powershell
make clean
make dev
```
