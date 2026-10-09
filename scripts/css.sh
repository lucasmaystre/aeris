#!/usr/bin/env bash
# Build server/static/app.css from server/assets/app.css with the Tailwind standalone CLI (no Node).
# Pass --watch to rebuild on every change. The built file is committed: Vercel doesn't build it.
set -euo pipefail
cd "$(dirname "$0")/.."
TAILWINDCSS_VERSION=v4.3.3 exec uv run tailwindcss \
  -i server/assets/app.css -o server/static/app.css --minify "$@"
