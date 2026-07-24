-- backend/scripts/init_db.sql
-- Runs automatically on first PostgreSQL container startup.
-- Enables the pgcrypto extension for gen_random_uuid() support.

CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
