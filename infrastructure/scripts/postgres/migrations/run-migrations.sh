#!/bin/sh
set -e

for file in /migrations/*.sql; do
  if [ -f "$file" ]; then
    echo "Applying migration: $file"
    psql -h postgres -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -c \
      "SELECT name FROM beliefcraft.schema_migrations WHERE name='$(basename $file)'" | grep -q "$(basename $file)" || \
      psql -h postgres -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -f "$file"
  fi
done
