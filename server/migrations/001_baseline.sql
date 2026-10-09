-- The schema as it was before migrations existed. Production already has this table.
CREATE TABLE IF NOT EXISTS note (
    id          serial PRIMARY KEY,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now(),
    content     text NOT NULL,
    deleted     boolean NOT NULL DEFAULT false
);
