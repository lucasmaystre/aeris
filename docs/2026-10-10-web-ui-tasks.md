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
- The style guide only uses classes the app uses, plus its own `sg-` styles; Tailwind no longer
  scans `dev/templates/` (E.1; it did from A.3 to D.5, adding about 3 KB gzipped to production).

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

From D.2 (2026-10-10):

- daisyUI maps the typography plugin's code blocks to `neutral` / `neutral-content` (near-black on
  white): `app.css` points them at `base-200` / `base-content`, with a 1px border. Links use the
  accent; headings are semibold, `h1` 28px, `h2` 22px, `h3` 18px. Body text unchanged (16px).
- Tags stay twice on a rendered note (badges above it, and its `Tags:` line as text): the user
  chose to keep it.

From D.3 (2026-10-10):

- The editor is one form: the same 57 px bar as the note view (title, the Markdown hint, Cancel,
  Save), an optional warning strip, then a borderless textarea filling the rest. Its text column
  matches the rendered note's exactly (x 344–1064 at 1280 px wide, measured); the right padding keeps
  the field itself full width, so clicking anywhere below the bar edits.
- Cancel on a new note re-requests the current page and swaps in its main panel: the note at
  `/n/42`, or the empty view at `/`. First done in `app.js` (`htmx.ajax` with `select`); the user
  then saw it do nothing, most likely a cached `app.js` without the handler. Now pure htmx
  (`hx-get=""` requests the current URL, `hx-select="#main-panel > *"`), like the editing Cancel.

From D.4 and D.5 (2026-10-11):

- Raw mode is the editor's read-only twin: a boxless `<pre>` with the textarea's font, spacing and
  column, and no tag badges. Measured identical (text at x 344–1064, top 130, Geist Mono 14/22.75).
- The note bar is muted: daisyUI's `tabs-box` for Rendered/Raw (grey track, white active tab), ghost
  Edit and Delete with small icons, Delete grey until hovered (then red). The editor's Save stays
  the one indigo button.
- New gallery view `note-raw`.

From E.1 (2026-10-11):

- Changes: one `message.html` for the empty, deleted and not-found views (not-found was inline HTML
  in `web.py` with a raw `text-red-600`, and a second copy in `index.html`); `pane-bar` and
  `note-source` utilities in `app.css` hold the bar's 57 px and the source column's recipe; no
  `hx-swap="innerHTML"` (htmx's default); `app.js` reorganized by topic with one listener per event;
  `_detail_context` shared by `/n/{id}` and the partial; `_form` takes named arguments; unused CSS
  (`.select-sm`, `.select:focus`, `.textarea:focus`) and the `ago` filter removed.
- Production CSS: 17.4 → 12.6 KB gzipped.
- Checked pixel by pixel: before/after galleries shot back to back differ only where relative times
  ("x minutes ago") are drawn; the style guide changed on purpose.
- Don't `git stash` with the sandbox running: its CSS watcher rebuilt `app.css` meanwhile and the
  stash wouldn't pop (recovered, verified identical).

From F.1 (2026-10-11):

- `deploy.yml`: unit tests, `vercel@63.1.0 deploy --prod` from `server/`, then `/healthz`. The
  secrets (`VERCEL_TOKEN`, `VERCEL_ORG_ID`, `VERCEL_PROJECT_ID`) are environment secrets of the
  `production` environment, so other workflows can't read the token.
- First run (manual): green in 70 s, a new production deployment on Vercel. Pushes that don't touch
  `server/` (docs, the CLI) don't deploy; `gh workflow run deploy.yml` deploys by hand.

From G.1 (2026-10-11):

- The gallery has a third size, 375×812 (an iPhone 13 mini, the user's phone). Below 768 px wide
  it emulates a phone (touch, no hover, mobile viewport), so `(hover: none)` and
  `(pointer: coarse)` queries match. 36 screenshots, about 30 s.
- At 375 px: the sidebar keeps its 320 px and leaves the main panel 55 px. Notes wrap one word per
  line, the editor one or two characters; the note bar's 313 px of controls are clipped; the empty
  view's message wraps to five lines. The page itself doesn't scroll sideways.
- The search box, the editor and the login field are 14 px: iOS Safari zooms in on focusing fields
  under 16 px (G.4).
- The top bar fits as is (New note and Log out), and so does the login page.
- Chromium's emulation can't show iOS Safari's toolbar (the `h-screen` vs `dvh` question): check
  on a real phone (G.4, G.5).

From G.2 (2026-10-11):

- Below `md` (768 px) the sidebar is full width and the main panel lies over it (`absolute
  inset-0`), shown only when it holds a view with a `pane-bar` (a note, the editor): Tailwind's
  `max-md:not-has-[.pane-bar]:hidden`, no JS. htmx swaps, history restores and direct loads all
  follow from the DOM.
- The note bar has a back chevron on phones: it swaps in `/`'s main panel (the empty message, so
  the list shows) and pushes `/`. The editor needs none: Cancel goes back to the note, or to the
  list for a new note.
- Covering the list rather than hiding it keeps its scroll and search when going back with the
  chevron. The browser's Back restores htmx's snapshot instead: the page's HTML, which lost the
  search box's typed value (on desktop too). `app.js` now writes it into the HTML before each
  snapshot, so Back keeps the filter or the ranking; the list's scroll still resets.
- On phones the deleted and not-found messages don't show (the list does): accepted.
- Desktop unchanged: 20 of 24 desktop shots pixel-identical to G.1's; the others differ only in
  relative times and antialiasing (21 pixels, intensity 2).

From G.3 (2026-10-11):

- On phones the note bar shows the back button, the ID, Rendered/Raw and icon-only Edit and Delete
  (`max-md:btn-square`, labels `max-md:sr-only`), measured without overflow at 375 px. The created
  and edited times are hidden there; the list row has the last update.
- The top bar and the editor bar already fit at 375 px: unchanged (the `+` icon idea dropped).
- Desktop unchanged: every desktop shot identical to G.2's but noise (6 pixels, intensity 1) and
  the style guide's relative times.

From G.4 (2026-10-11):

- Touch details use Tailwind's `pointer-coarse:` variant, not the width: iOS zooms in on fields
  under 16 px on an iPad too. The search box, the editor, Raw mode (the editor's twin) and the
  login field are 16 px on touch screens; the `/` hint is hidden there.
- The body is `h-dvh` (was `h-screen`): iOS Safari's `100vh` is taller than the visible area while
  its toolbar shows. Same on desktop; Chromium can't show the difference (G.5).
- The search box has no autocorrect, auto-capitalization or spellcheck.
- The placeholder fits at 16 px (258 of 325 px at 375 wide); kept. The iPhone's keyboard calls
  Enter "search", so "Enter to rank" is slightly off there.
- Desktop unchanged: same noise as before (a code block's antialiasing, relative times).

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
- [x] D.2 Content styling: softer prose, light code blocks (W11)
- [x] D.3 Editor fills the area below the bar (W14)
- [x] D.4 Raw view as the editor's read-only twin: no box, same font and column
- [x] D.5 A more muted note bar: segmented Rendered/Raw, quiet Edit and Delete

## Phase E: Cleanup

- [x] E.1 Web UI code review: one message view, shared bar and source-text utilities, `app.js`
  organized by topic, leftovers removed, style guide trimmed to what the app uses

## Phase F: Deploys

- [x] F.1 Deploy from GitHub Actions on every push to `main` that touches `server/`, after the unit
  tests (like PyPI publishing)

## Phase G: Mobile

Below 768 px, one pane at a time: the list on `/`, a note or the editor full-screen with a back
button. Desktop stays pixel-identical.

- [x] G.1 Phone size (375×812) in the screenshot gallery; findings
- [x] G.2 One pane at a time: list or note full-screen, a back button, browser Back works
- [x] G.3 Bars that fit: the note bar's ID alone and icon-only Edit/Delete on phones
- [x] G.4 Touch details: 16 px fields (no iOS zoom), `dvh` heights, no `/` hint on touch, no
  autocorrect in search; the placeholder and the login page fit as they are
- [ ] G.5 Check on a real phone (production), fix what turns up

## Backlog

- Syntax highlighting in code blocks (` ```python `).
- `#` autocomplete in the search box (type `#la`, pick a tag), if tags grow (C.4).
