#!/bin/sh
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
  SELECT 'CREATE DATABASE ${ENVIRONMENT_DB}'
  WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '${ENVIRONMENT_DB}')\gexec

  SELECT 'CREATE DATABASE ${RAG_DB}'
  WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '${RAG_DB}')\gexec
EOSQL
