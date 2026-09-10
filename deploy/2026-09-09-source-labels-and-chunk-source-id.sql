-- Columns added for search-payload parity and for importing an existing index.
--
-- The schema is created with SQLAlchemy `create_all`, which adds missing tables
-- but never missing columns, and the repository carries no Alembic revisions.
-- Run this against any database created before these columns existed:
--
--   docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
--     -f - < deploy/2026-09-09-source-labels-and-chunk-source-id.sql
--
-- Every statement is idempotent.

-- Written into the search payload as `source` and `source_mr`. `source_mr` was
-- hardcoded to an empty string before this.
ALTER TABLE documents ADD COLUMN IF NOT EXISTS source_label    varchar(256);
ALTER TABLE documents ADD COLUMN IF NOT EXISTS source_label_mr varchar(256);

-- Reserved for per-document metadata; nothing writes to it yet.
ALTER TABLE documents ADD COLUMN IF NOT EXISTS metadata_json   jsonb;

-- Set only on chunks imported from an existing collection. The indexer keys the
-- search point off this when present, so re-indexing overwrites the imported
-- point instead of adding a second one under a freshly generated id.
ALTER TABLE chunks    ADD COLUMN IF NOT EXISTS source_chunk_id varchar(128);
CREATE INDEX IF NOT EXISTS ix_chunks_source_chunk_id ON chunks (source_chunk_id);
