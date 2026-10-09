-- Semantic search (phase 4). Pinned to `public`: extensions are per database, not per schema.
CREATE EXTENSION IF NOT EXISTS vector SCHEMA public;

-- One embedding per note. The dimension isn't fixed, so switching embedding models needs only a
-- reindex, not a migration; `model` records which model produced each vector.
CREATE TABLE note_embedding (
    note_id       int PRIMARY KEY REFERENCES note(id),
    model         text NOT NULL,
    content_hash  text NOT NULL,  -- sha256 of the embedded content; a mismatch means stale.
    embedding     vector NOT NULL
);
