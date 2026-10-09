-- Tags are derived from content by the server; `aeris-admin recompute-tags` backfills them.
ALTER TABLE note ADD COLUMN tags text[] NOT NULL DEFAULT '{}';

-- A snapshot of a note's previous content, taken on every update.
CREATE TABLE note_revision (
    id          serial PRIMARY KEY,
    note_id     int NOT NULL REFERENCES note(id),
    created_at  timestamptz NOT NULL DEFAULT now(),
    content     text NOT NULL
);

CREATE INDEX note_revision_note_id_idx ON note_revision (note_id);
