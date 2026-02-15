CREATE SCHEMA IF NOT EXISTS beliefcraft;

CREATE TABLE IF NOT EXISTS beliefcraft.schema_migrations (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO beliefcraft.schema_migrations (name)
VALUES ('001_initial_schema')
ON CONFLICT (name) DO NOTHING;
