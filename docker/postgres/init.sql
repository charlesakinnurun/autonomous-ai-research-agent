-- Extensions required by the application.
-- pgvector image ships with vector; pg_trgm and pgcrypto cover hybrid search and UUIDs.
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
