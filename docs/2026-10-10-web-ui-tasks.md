# aeris — Web UI Task List

Status: 2026-10-10. Implements `2026-10-10-web-ui.md`, in small tasks. Each task is planned,
agreed, implemented, reviewed, then committed on its own (aesthetic tweaks: one task per polish
pass).

Decisions:

- Check UI changes with a UI sandbox and a Playwright screenshot gallery; tune the look on a
  dev-only style guide page (doc §2).
- Inspiration screenshots stay local (`docs/aesthetics-inspiration/` is gitignored): they show
  personal tabs and accounts, and the repo is public.
- Light only, no dark mode. A little color, not greyscale. daisyUI components first (doc §3).
- Tag filter: our own small component, not a third-party library.
- The style guide's template (`dev/templates/`) is a Tailwind source, so the production CSS also
  carries the components it shows: about 3 KB gzipped (11 → 14.5 KB). Accepted while we choose
  components; the gap shrinks as the app adopts them (A.3).

## Findings

From A.1 (2026-10-10):

- The sandbox's first screenshot already shows W3 (uneven spacing) and W6 (previews overflow the
  sidebar's width).
- A note that starts with a code fence gets the title `` `bash `` (`parsing.title` keeps the fence's
  backtick and language). Fix with the sidebar rows (C.1).
- The sandbox stops cleanly on Ctrl-C (SIGINT), emptying the test branch; unlike `fastapi dev`,
  nothing lingers on the port.

From A.2 (2026-10-10):

- A second sandbox, started while the user's was running, reseeded the shared test branch and
  emptied it on exit, leaving the first one with no notes. The sandbox now checks the port before
  touching the database.
- The gallery: 9 views × 2 widths in about 20 s. It shows W6 (the relative time exists but is
  clipped off the sidebar's right edge), W10, W11 and W14 clearly.
- Search snippets show raw Markdown (`# Title`, `Tags: …`): fix with the sidebar rows (C.1).

From A.3 (2026-10-10):

- The editor partial fills its container (`h-full`, a textarea of at least 16 rem); with the
  conflict warning it needs about 28 rem, else it scrolls inside the main panel. Revisit in D.3.
- Unfocused inputs and textareas have a nearly invisible border (W8 applies to the editor too):
  B.1's tokens.

## Phase A: Tooling

- [x] A.1 UI sandbox: one command for a seeded dev server on the test branch (fixture notes, dev
  token, fake embedder, cleanup)
- [x] A.2 Screenshot gallery with Playwright: fixed views, desktop and narrow widths
- [x] A.3 Style guide page (dev only): every component, real templates, fixture data

## Phase B: Look

- [ ] B.1 Palette, fonts and type scale on the style guide: compare the three palettes and Geist
  vs Inter (§3); then retheme the whole UI with the chosen tokens
- [ ] B.2 Top bar: drop the user's name, "New note" moves in (W1, W2)

## Phase C: Sidebar

- [ ] C.1 Note rows: equal height, title / ID + relative time / preview, dividers, no horizontal
  scroll, light-grey selection (W3–W6, W10)
- [ ] C.2 New notes appear in the list at once (W7: investigate first)
- [ ] C.3 Search box with a visible border (W8)
- [ ] C.4 Tag filter for ~100 tags: dropdown, type-to-filter, checkboxes (W9)

## Phase D: Note pane

- [ ] D.1 Full-width header bar, edge-to-edge border, fixed while the note scrolls (W12, W13)
- [ ] D.2 Content styling: softer prose, light code blocks (W11)
- [ ] D.3 Editor fills the area below the bar (W14)

## Backlog

- Syntax highlighting in code blocks (` ```python `).
