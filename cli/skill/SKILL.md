---
name: aeris
description: Read and write the user's personal notes with the `aeris` CLI. Use when the user mentions their notes, asks what they wrote or know about something, or asks you to remember, record, jot down or update something.
---

# aeris: the user's notes

`aeris` is a CLI for the user's personal notes, which live on a server. Notes are Markdown; the
first line is the title (a leading `#` is optional). Every note has a numeric ID.

Always pass `--json`: output is then the server's JSON on stdout. Exit codes: 0 success, 1 error,
2 usage error. On error, stdout is `{"error": "...", "status": 409}`; `status` (the HTTP status)
is absent for errors such as a missing configuration or an unreachable server.

## Check the setup

Run `aeris tags --json` first: exit code 0 means the CLI works (the list may be empty). If it
fails with a configuration error, the CLI needs `AERIS_URL`
and `AERIS_TOKEN` (or `url` and `token` in `~/.aeris.yaml`). Ask the user for them; never guess
or search the machine for a token.

## Read

1. Find candidates, using both kinds of search when unsure:
   - `aeris search WORDS... --json`: notes containing the exact phrase (ignoring case and
     accents), newest first. Best for names, commands, error messages.
   - `aeris ask WORDS... --json`: notes closest in meaning, best first, with a `score` (cosine
     similarity). Best for questions and vague topics. Scores are relative: a good match is often
     only 0.3 to 0.5, so compare hits with each other, not with a fixed bar.
   - `aeris list --last "2 days" --json`: notes created recently, newest first. For "what's new",
     also run it with `--order updated` to catch recent edits (what changed isn't recorded).
     `--last` takes minutes, hours, days or weeks (`"3h"`, `"2 weeks"`), or a date
     (`2026-10-01`); not months.
   - `--tag T` keeps notes with tag `T` or its children; `--limit N` changes how many come back
     (10 for `ask`, 30 otherwise).
2. Fetch the promising hits in one call: `aeris show 12 27 31 --json` returns `{"notes": [...],
   "missing": [...]}`. Search hits carry only a title and a snippet, and `list` omits content,
   so read the full notes before answering.
3. Answer from the notes and cite them by ID ("note #27"). If the notes don't say, say so; don't
   fill gaps with guesses presented as the user's notes.

## Write

Pass text with `-m` or on stdin; never rely on an editor (there's no terminal).

- **Add to an existing note** (the default for new information on a known topic):
  `aeris append ID -m "TEXT" --json`. It adds a paragraph and never conflicts.
- **New topic:** `aeris add --json` with the content on stdin: a title line, the tags line right
  under it (so later appends don't bury it), then the body:

  ```bash
  aeris add --json <<'EOF'
  # Kubernetes node selectors
  Tags: #infra/kubernetes

  Pin the frontend to AVX2 nodes with `feature.node.kubernetes.io/cpu-cpuid.AVX2: "true"`.
  EOF
  ```

- **Rewrite a note** (only when asked to change or reorganize existing text):
  1. `aeris show ID --json` and keep its `updated_at`.
  2. `aeris edit ID --stdin --expected-updated-at UPDATED_AT --json` with the full new content
     on stdin.
  3. If it fails with `"status": 409`, the note changed meanwhile; the error's `current` is the
     latest version. Merge your change into it and try again with `current.updated_at`, passed
     as is. Never drop the other change.
- **Delete** only when the user asks: `aeris delete ID --json`. Deleted notes disappear from
  every command but are kept in the database, so the user can recover them.

Write notes for the user to read later: clear, self-contained, no chat filler. Before adding a
note, check with `search`/`ask` that one on the topic doesn't already exist; prefer appending to it.

## Tags

- Tags come only from a line like `Tags: #project/aeris, #ideas`, placed right under the title.
  Inline `#words` elsewhere are not tags.
- Lowercase; `/` makes a hierarchy (`--tag project` also matches `project/aeris`).
- Reuse existing tags (`aeris tags --json` lists them with counts) rather than inventing
  near-duplicates. Add tags sparingly: one to three per note.

## JSON shapes

- Note: `{"id", "title", "tags", "created_at", "updated_at", "content", "deleted"}`.
- `list`, `show`: `{"notes": [note...], "missing": [id...]}`. `list` sets `content` to null.
  `show` exits 1 if any ID is missing, but still prints the notes it found.
- `search`, `ask`: `{"hits": [{"id", "title", "tags", "created_at", "updated_at", "snippet",
  "score"}...]}`; `score` is null for `search`.
- `tags`: `{"tags": [{"tag", "count"}...]}`.
- `add`, `append`, `edit`: the saved note. `delete`: `{"id", "deleted": true}`.
