# aeris

The command-line client for aeris, a personal notes app used by humans (a web UI) and AI agents
(this CLI). It talks to an aeris server over HTTP; it never touches the database.

## Install

```bash
uv tool install aeris
```

## Configure

Point the CLI at your server with a URL and a token's secret, either as environment variables
(handy in agent sandboxes):

```bash
export AERIS_URL=https://your-aeris.vercel.app
export AERIS_TOKEN=your-secret
```

or in `~/.aeris.yaml` (another file can be named with `AERIS_CONFIG_PATH`):

```yaml
url: https://your-aeris.vercel.app
token: your-secret
```

Environment variables win over the file.

## Use

```bash
aeris list [--limit 30] [--last "2 days"] [--tag T] [--order created|updated]
aeris show ID [ID...]
aeris search WORDS... [--tag T] [--limit 30]     # phrase search, ignoring case and accents
aeris ask WORDS... [--tag T] [--limit 10]        # closest notes in meaning, with scores
aeris tags
aeris add [-m TEXT]                              # else piped stdin, else your editor
aeris append ID [-m TEXT]                        # adds a paragraph; never conflicts
aeris edit ID                                    # in your editor
aeris edit ID --stdin [--expected-updated-at T]  # from stdin, for scripts and agents
aeris delete ID
aeris export [PATH | -] [--force]                # every note as JSON Lines: a backup
```

`ask` ranks notes by semantic similarity (cosine, higher is closer). Scores are relative: a good
match often scores only 0.3–0.5, so compare results with each other rather than with a fixed bar.

Tags come from lines like `Tags: #project/aeris, #ideas` in a note. The editor is `$VISUAL`, else
`$EDITOR`, else `vi`; it only opens in an interactive terminal.

## For agents and scripts

- Add `--json` to any command (except `export`) to get the server's JSON.
- Exit codes: 0 success, 1 error, 2 usage error.
- With `--json`, errors are JSON on stdout: `{"error": ..., "status": ...}`. An edit conflict
  (409) also carries `current`, the note's latest version.
- Prefer `append` to add information. To rewrite a note safely, read its `updated_at` with
  `show --json`, then `edit --stdin --expected-updated-at` that value: the edit fails instead of
  overwriting someone else's change.

## Upgrading from 0.4

0.5 talks to the aeris server instead of the database:

- `~/.aeris.yaml` needs `url` and `token` instead of `database_url`.
- `display` is now `show`; `list` shows the newest notes first.
- `web` and `reset-db` are gone: the web UI is part of the server.
