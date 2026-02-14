#!/bin/sh
set -e

for file in /migrations/*.sql; do
  if [ -f "$file" ]; then
    echo "Applying migration: $file"
    psql -h postgres -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -f "$file"
  fi
done
