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
- The sidebar lists notes by last update, and rows show no tag badges (C.1).
- Creating a note clears the search box and closes the ranking, so the new note shows (C.2). Notes
  added elsewhere (CLI, agents, another tab) appear on the next reload: no refresh on focus or
  polling (C.2).
- Focus: a darker border, no ring, on every field (C.3: the indigo ring from B.1b felt heavy).
- `/` anywhere outside a text field focuses the search box; a `/` hint shows in the box until it
  has focus or text (C.3). The first piece of keyboard navigation (backlog).
- Search snippets stay raw Markdown (C.5, dropped): they show exactly what matched, and a plain-text
  index would stop link URLs and `Tags:` lines from matching, and change the CLI's search.
- Tags filter through the search box only (C.4): type `#tag`, or click a tag on an open note. The
  tag chips above the list are gone (they don't scale to ~100 tags). A Tags dropdown was built and
  dropped: redundant with the search box, and it squeezed it.
- Theme: slate neutrals + indigo accent (`#4f46e5`). Font: Inter for text, Geist Mono for code and
  IDs (B.1a, picked from the style guide and a side-by-side gallery).
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

From B.1 (2026-10-10):

- Galleries made the comparison easy: three palettes and two fonts on every real page, side by
  side (`--compare`). The scaffolding (candidate themes, `--theme`/`--font`, the switcher) was
  removed once the choice was made; `--compare` stays for before/after.
- The retheme fixes W8 (visible search border) as a side effect. Still to do: the black selected
  note (C.1, W10) and dark code blocks (D.2, W11).
- daisyUI draws the focus ring in the text color (a black double ring); `app.css` points it at the
  accent.

From C.1 (2026-10-10):

- Rows: one partial (`note_row.html`) for the list and the ranking, a fixed shape (title; `#ID ·
  relative time`; two preview lines), so every row is the same height. No tag badges: tags stay on
  the note and in the tag filter.
- The list shows and sorts by last update (a decision).
- daisyUI's `list` wasn't used: its dividers are 5% black and inset, its rows rounded; Tailwind's
  `divide-y` gives full-width slate lines.
- Relative times are `<time data-ago>`, refreshed every minute by `app.js` (they used to freeze at
  render time). Selection is `aria-current="page"`, styled with the accent tint and a left bar.

From C.2 (2026-10-10):

- Creating a note always reloaded the list (`HX-Trigger: noteCreated`), but an active search filter
  hid the new row at once, and ranked results covered the list. Reproduced in the sandbox; both
  fixed by one `noteCreated` listener in `app.js`.
- The sandbox serves static files without `Cache-Control`: after JS or CSS changes, hard-refresh
  (the stale `app.js` explained a missing selection highlight during C.1's review).

From C.4 (2026-10-10):

- The dropdown worked (filter field, checkboxes, counts, Clear), but in use it duplicated the search
  box. Real notes have no tags yet anyway (see 5.2). If tags grow, `#` autocomplete in the search
  box would scale without a second control (backlog).
- The gallery caught the dropdown mid-animation (Playwright acts faster than its 200 ms opening):
  `settle` now also waits for running CSS animations; kept.

From D.1 (2026-10-10):

- First version: the bar was `sticky` inside the scrolling main panel. In review, the scrollbar ran
  alongside the bar and macOS's elastic overscroll dragged it ("jiggle"). Now the main panel doesn't
  scroll: the note view is a fixed bar plus its own scrolling body (`.note-body`), and the editor
  scrolls itself if needed.
- The sidebar's line sits under the search row (it was the list's top border, so it scrolled away).
  Both lines are 57 px from the top bar, on the same pixel row (measured in the browser).
- Tags moved from the bar to the top of the content. The rendered note also shows its `Tags:` line
  as text, so tags appear twice: for D.2.
- New gallery view `note-scrolled`: the long note scrolled by 900 px.

## Phase A: Tooling

- [x] A.1 UI sandbox: one command for a seeded dev server on the test branch (fixture notes, dev
  token, fake embedder, cleanup)
- [x] A.2 Screenshot gallery with Playwright: fixed views, desktop and narrow widths
- [x] A.3 Style guide page (dev only): every component, real templates, fixture data

## Phase B: Look

- [x] B.1a Compare: three candidate themes (slate + indigo, stone + emerald, zinc + violet) and
  Geist vs Inter, on the style guide (switcher) and in screenshot galleries (`--theme`, `--font`,
  `--compare`); the user picks
- [x] B.1b Apply: the chosen theme and font only, one type scale everywhere (deploy later)
- [x] B.2 Top bar: drop the user's name, "New note" moves in (W1, W2)

## Phase C: Sidebar

- [x] C.1 Note rows: equal height, title / ID + relative time / preview, dividers, no horizontal
  scroll, light-grey selection (W3–W6, W10)
- [x] C.2 New notes appear in the list at once (W7: investigate first)
- [x] C.3 Search box with a visible border (W8, done by the retheme); `/` focuses it
- [x] C.4 Tags (W9): chips removed; filter by `#tag` in the search box (a dropdown was tried and
  dropped)
- [x] C.5 Search snippets as plain text: dropped, raw snippets stay

## Phase D: Note pane

- [x] D.1 Full-width header bar, edge-to-edge border, fixed while the note scrolls (W12, W13)
- [ ] D.2 Content styling: softer prose, light code blocks (W11)
- [ ] D.3 Editor fills the area below the bar (W14)

## Backlog

- Syntax highlighting in code blocks (` ```python `).
- `#` autocomplete in the search box (type `#la`, pick a tag), if tags grow (C.4).
