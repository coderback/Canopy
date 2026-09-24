-- Runs once when the Postgres container is first created.
-- `canopy` (from POSTGRES_USER) owns the schema and runs migrations.
-- `canopy_app` is what the API and worker connect as. It does not own any table,
-- so row-level security applies to it (table owners bypass RLS).
-- Development passwords only; production credentials come from the secret store.
CREATE ROLE canopy_app LOGIN PASSWORD 'canopy_app';
GRANT CONNECT ON DATABASE canopy TO canopy_app;

CREATE DATABASE canopy_test OWNER canopy;
GRANT CONNECT ON DATABASE canopy_test TO canopy_app;
