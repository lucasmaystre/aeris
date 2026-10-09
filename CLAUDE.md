# aeris

A single-user notes app. Humans use a web UI; AI agents use a CLI that talks to the same server
over a JSON API. Notes live in Neon Postgres.

- Big picture: `docs/2026-10-09-design.md`.
- Progress, decisions and findings: `docs/2026-10-09-tasks.md`.

## How we work

- Small tasks from the task list. For each: propose a short plan, agree on it, implement, review
  together, then commit.
- One commit per task, ticking it in the task list. Messages are sentences ending with a period,
  e.g. `Scaffold server package (task 1.1).`
- Record decisions and findings in the task list. Keep this file lean.

## Layout

- `server/`: the FastAPI app (`aeris_server`) and the Vercel project root.
- `cli/`: the new CLI (`aeris_cli`), an HTTP client of the server. Until task 2.5 it's packaged as
  `aeris-cli` with the command `aeris-next`; then both become `aeris`.
- `aeris/`: the old CLI, talking to the database directly. Leave it untouched until task 2.5.

## Stack

Don't mix syntax from other major versions: Python 3.14, FastAPI, SQLAlchemy 2, psycopg 3, Jinja2.
Phase 3 adds htmx 2, Tailwind CSS v4 (CSS-first `@theme`, no `tailwind.config.js`) and daisyUI v5.

## Conventions

- The server owns all database access and business logic; the CLI is a thin HTTP client.
- Routes are thin wrappers around the service layer (`aeris_server/notes.py`). Service functions
  take a `Session` and commit their own writes.
- `server/pyproject.toml` lists runtime dependencies only (it's bundled for Vercel); dev tools go
  in the root `dev` group.
- Migrations are numbered SQL files in `server/migrations/`. Never edit one that has run on
  production; add a new one. They run as `neondb_owner`; the server runs as `agent` (rows only).

## Commands

From the repo root. Lint `server` and `cli` only: the old `aeris/` doesn't pass.

```bash
uv run pytest                        # all tests (server and cli)
uv run pytest -m "not db"            # unit tests only: offline, no setup
uv run ruff check server cli conftest.py && uv run ruff format server cli conftest.py && uv run pyright server cli conftest.py
uv run fastapi dev server/main.py    # dev server
uv run aeris-admin migrate           # apply migrations to AERIS_DATABASE_URL
cd server && vercel deploy --prod    # deploy (Vercel CLI; no Git integration)
```

## Secrets and databases

- Local secrets live in the root `.env` (gitignored). Never print or commit them.
- `AERIS_TOKENS` holds API tokens as `name:ro|rw:secret`, comma-separated. Generate secrets with
  `python -c "import secrets; print(secrets.token_urlsafe(32))"`.
- Tests marked `db` (automatic for the `database` and `empty_database` fixtures) need
  `AERIS_TEST_DATABASE_URL`, a Neon branch with no real notes; they skip without it.
- `server/.vercelignore` keeps `.env*` and tests out of deploys. Keep it that way.
