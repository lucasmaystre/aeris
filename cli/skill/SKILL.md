---
name: aeris
description: Search and read the user's personal notes with the `aeris` CLI (read-only). Use when the user mentions their notes, or asks what they wrote or know about something.
---

# aeris: the user's notes

`aeris` is a CLI for the user's personal notes, which live on a server. Notes are Markdown; the
first line is the title (a leading `#` is optional). Every note has a numeric ID.

Access is read-only: never run `add`, `edit` or `delete` (the server refuses them). If the user
asks you to save something, draft the note (a title line, then the text) and suggest they add it
themselves with `aeris add`.

Always pass `--json`: output is then the server's JSON on stdout. Exit codes: 0 success, 1 error,
2 usage error. On error, stdout is `{"error": "...", "status": 404}`; `status` (the HTTP status)
is absent for errors such as a missing configuration or an unreachable server.

## Check the setup

Run `aeris tags --json` first: exit code 0 means the CLI works (the list may be empty). If it
fails with a configuration error, the CLI needs `AERIS_URL` and `AERIS_TOKEN` (or `url` and
`token` in `~/.aeris.yaml`). Ask the user for them; never guess or search the machine for a token.

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

## Tags

Tags come only from a line like `Tags: #project/aeris, #ideas` under a note's title. They're
lowercase, and `/` makes a hierarchy: `--tag project` also matches `project/aeris`.
`aeris tags --json` lists them with counts.

## JSON shapes

- Note: `{"id", "title", "tags", "created_at", "updated_at", "content", "deleted"}`.
- `list`, `show`: `{"notes": [note...], "missing": [id...]}`. `list` sets `content` to null.
  `show` exits 1 if any ID is missing, but still prints the notes it found.
- `search`, `ask`: `{"hits": [{"id", "title", "tags", "created_at", "updated_at", "snippet",
  "score"}...]}`; `score` is null for `search`.
- `tags`: `{"tags": [{"tag", "count"}...]}`.
