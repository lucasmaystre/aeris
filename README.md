# aeris

A personal notes app, used two ways: humans through a web UI reachable from anywhere, and AI
agents through a command-line client. Notes are Markdown, stored in Postgres.

- `server/`: a FastAPI app with the web UI (Jinja + htmx) and a JSON API, deployed to Vercel and
  backed by Neon Postgres.
- `cli/`: the `aeris` command-line client, published to PyPI. See [cli/README.md](cli/README.md)
  to install and use it.

The design is in [docs/2026-10-09-design.md](docs/2026-10-09-design.md), and progress in
[docs/2026-10-09-tasks.md](docs/2026-10-09-tasks.md).

## Development

The repo is a uv workspace. `uv sync` installs everything; [CLAUDE.md](CLAUDE.md) lists the
commands to test, lint, run and deploy, and the conventions to follow.
