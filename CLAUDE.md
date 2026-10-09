# aeris

A single-user notes app. Humans use a web UI; AI agents use a CLI that talks to the same server
over a JSON API. Notes live in Neon Postgres.

- Big picture: `docs/2026-10-09-design.md`.
- Progress, decisions and findings: `docs/2026-10-09-tasks.md`.

## How we work

- Work proceeds in small tasks from the task list. For each one: propose a short plan, agree on it,
  implement, review together, then commit.
- One commit per task, ticking the task in the task list in the same commit. Commit messages are
  sentences ending with a period, e.g. `Scaffold server package (task 1.1).`
- Record new decisions and findings in the task list, not only in the conversation.

## Repo layout

- `server/`: the new FastAPI app (package `aeris_server`). This is the Vercel project root.
  - `main.py`: entrypoint for Vercel and `fastapi dev`; the app itself is in `aeris_server/app.py`.
  - `static/`: static assets, mounted at `/static` (Vercel serves the mount from its CDN).
- `aeris/`: the old CLI + web app, talking to the database directly. Leave it untouched; the new
  `cli/` replaces it in task 2.5.
- `docs/`: dated design docs and the task list.

The root `pyproject.toml` is a uv workspace with `server` as a member; one `uv.lock` and one `.venv`
cover everything.

## Stack and versions

Don't mix syntax from other major versions.

- Python 3.14 locally and on Vercel (`requires-python = ">=3.13"`).
- FastAPI, Jinja2, SQLAlchemy 2, psycopg 3, markdown2.
- Planned (phase 3): htmx 2, Tailwind CSS v4 (CSS-first config with `@theme`, no
  `tailwind.config.js`), daisyUI v5, `@tailwindcss/typography`.

## Conventions

- The server owns every database query and all business logic. The CLI is a thin HTTP client.
- Routes (web and `/api`) are thin wrappers around the service layer.
- `server/pyproject.toml` lists runtime dependencies only; dev tools go in the root `dev` group.
  Everything in `server/` is bundled into the Vercel function.

## Commands

Run from the repo root.

```bash
uv sync                                  # install everything
uv run pytest server                     # tests
uv run ruff check server                 # lint
uv run ruff format server                # format
uv run pyright server                    # type-check
uv run fastapi dev server/main.py        # dev server on http://127.0.0.1:8000
```

Lint and format `server` only: the old `aeris/` package doesn't pass. Pyright may warn that a newer
version exists; that warning is harmless.

## Environment and databases

- The server reads `AERIS_DATABASE_URL`. Neon's `postgresql://…` strings work as-is; use the
  pooled one (host contains `-pooler`).
- Local secrets go in the root `.env` (gitignored); tests load it. Never print or commit its values.
- `AERIS_TEST_DATABASE_URL` points at the Neon branch `test` (schema-only, no real notes). Tests
  that need Postgres use the `database` fixture, which skips them when the variable is unset.

Deploy (production, via the Vercel CLI; there is no Git integration):

```bash
cd server && vercel deploy --prod
```

## Gotchas

- `server/.vercelignore` keeps `.env*`, tests and caches out of the upload. Keep it that way.
- `server/.vercel/` and `server/.env.local` are created by `vercel link`; never commit them.
- The function runs in `iad1` until task 1.18 moves it to `lhr1`, next to Neon (`eu-west-2`).
