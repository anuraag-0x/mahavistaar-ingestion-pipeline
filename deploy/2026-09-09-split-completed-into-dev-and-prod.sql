-- `completed` used to mean "published to the dev index" and was the only end of
-- the pipeline. Production publishing adds a second one, so the two are named:
--
--   dev_completed   in the dev index, not yet promoted
--   prod_completed  in the production index
--
-- Existing rows were all published to dev, so they become dev_completed.
--
--   docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
--     -f - < deploy/2026-09-09-split-completed-into-dev-and-prod.sql
--
-- Idempotent: re-running matches nothing.

UPDATE documents      SET stage         = 'dev_completed' WHERE stage         = 'completed';
UPDATE document_jobs  SET current_stage = 'dev_completed' WHERE current_stage = 'completed';
