// aeris: small browser-side behaviour, loaded on every page after htmx.

// Show <time datetime="..."> elements in the viewer's timezone, e.g. "2026-10-09 19:59", with the
// full date and timezone as a tooltip. The server renders them in UTC as a fallback.
function localizeTimes(root) {
  const pad = (number) => String(number).padStart(2, "0");
  for (const element of root.querySelectorAll("time[datetime]")) {
    const moment = new Date(element.getAttribute("datetime"));
    if (Number.isNaN(moment.getTime())) continue;
    element.textContent =
      `${moment.getFullYear()}-${pad(moment.getMonth() + 1)}-${pad(moment.getDate())} ` +
      `${pad(moment.getHours())}:${pad(moment.getMinutes())}`;
    element.title = moment.toLocaleString(undefined, {
      weekday: "long", year: "numeric", month: "long", day: "numeric",
      hour: "2-digit", minute: "2-digit", timeZoneName: "short",
    });
  }
}

// Runs on the initial page and on every fragment htmx swaps in.
htmx.onLoad(localizeTimes);

// Search: filter the sidebar as you type, ignoring case, accents and whitespace runs. The steps
// mirror `normalize` in server/aeris_server/parsing.py: change them together. Words starting
// with `#` filter by tag instead, like the server's tag filter: `#project` matches `project/aeris`.

const SNIPPET_LENGTH = 120;
const searchIndex = new WeakMap(); // Sidebar item -> its text, normalized, with origins.

function normalize(text) {
  return text.normalize("NFKD").replace(/\p{M}/gu, "").toLowerCase().replace(/\s+/g, " ");
}

// Normalize character by character, remembering where each normalized unit came from, so a match
// can be shown in the original text.
function indexText(text) {
  let normalized = "";
  const origins = [];
  let position = 0;
  for (const char of text) {
    for (let piece of char.normalize("NFKD").replace(/\p{M}/gu, "").toLowerCase()) {
      if (/\s/.test(piece)) {
        if (normalized.endsWith(" ")) continue;
        piece = " ";
      }
      normalized += piece;
      for (let unit = 0; unit < piece.length; unit++) origins.push(position);
    }
    position += char.length;
  }
  return { text, normalized, origins };
}

// The original text around a match, cut at words, as nodes: text, <mark>match</mark>, text.
function snippetNodes(entry, start, length) {
  const { text, origins } = entry;
  const from = origins[start];
  const end = start + length < origins.length ? origins[start + length] : text.length;
  const context = Math.max(0, Math.floor((SNIPPET_LENGTH - (end - from)) / 2));
  let low = Math.max(0, from - context);
  let high = Math.min(text.length, end + context);
  const space = low > 0 ? text.slice(low, from).search(/\s/) : -1;
  if (space >= 0) low += space + 1;
  const lastSpace = high < text.length ? text.slice(end, high).search(/\s\S*$/) : -1;
  if (lastSpace >= 0) high = end + lastSpace;
  const flat = (part) => part.replace(/\s+/g, " ");
  const mark = document.createElement("mark");
  mark.className = "bg-secondary text-secondary-content rounded-sm";
  mark.textContent = flat(text.slice(from, end)).trim();
  return [
    (low > 0 ? "…" : "") + flat(text.slice(low, from)).trimStart(),
    mark,
    flat(text.slice(end, high)).trimEnd() + (high < text.length ? "…" : ""),
  ];
}

// Split the search box into tag filters (`#word`, lowercased) and the phrase: as typed (`text`)
// and normalized (`phrase`).
function parseQuery(value) {
  const words = value.trim().split(/\s+/).filter(Boolean);
  const isTag = (word) => word.startsWith("#") && word.length > 1;
  const text = words.filter((word) => !isTag(word)).join(" ");
  return {
    tags: words.filter(isTag).map((word) => word.slice(1).toLowerCase()),
    text,
    phrase: normalize(text).trim(),
  };
}

function hasTags(item, tags) {
  const own = item.dataset.tags ? item.dataset.tags.split(" ") : [];
  return tags.every((tag) => own.some((t) => t === tag || t.startsWith(tag + "/")));
}

function applySearch() {
  const input = document.getElementById("search");
  const list = document.getElementById("note-list");
  if (!input || !list) return;
  const { tags, phrase: query } = parseQuery(input.value);
  for (const chip of document.querySelectorAll(".tag-chip[data-tag]")) {
    const active = tags.includes(chip.dataset.tag);
    chip.classList.toggle("badge-primary", active);
    chip.classList.toggle("badge-secondary", !active);
  }
  let shown = 0;
  for (const item of list.querySelectorAll("li[data-text]")) {
    let entry = searchIndex.get(item);
    if (!entry) {
      entry = indexText(item.dataset.text);
      searchIndex.set(item, entry);
    }
    const at = query ? entry.normalized.indexOf(query) : -1;
    const matches = (!query || at >= 0) && hasTags(item, tags);
    item.hidden = !matches;
    if (matches) shown++;
    const preview = item.querySelector(".preview");
    const snippet = item.querySelector(".snippet");
    if (preview) preview.hidden = at >= 0;
    snippet.hidden = at < 0;
    if (at >= 0) snippet.replaceChildren(...snippetNodes(entry, at, query.length));
  }
  const noMatches = list.querySelector(".no-matches");
  if (noMatches) noMatches.hidden = (!query && !tags.length) || shown > 0;
  const rankHint = list.querySelector(".rank-hint");
  if (rankHint) rankHint.hidden = !query;
}

// Ranking: Enter ranks notes by semantic similarity to the phrase (the server embeds it, so it
// takes about a second). The results stand in for the list; typing goes back to filtering.

function isRanking() {
  return !document.getElementById("ranked-notes")?.hidden;
}

function showRanking(on) {
  const list = document.getElementById("note-list-container");
  const ranked = document.getElementById("ranked-notes");
  if (!list || !ranked) return;
  list.hidden = on;
  ranked.hidden = !on;
}

function rank() {
  const input = document.getElementById("search");
  const ranked = document.getElementById("ranked-notes");
  if (!input || !ranked) return;
  const { tags, text } = parseQuery(input.value);
  if (!text) return;
  const params = new URLSearchParams({ q: text });
  for (const tag of tags) params.append("tag", tag);
  const waiting = document.createElement("p");
  waiting.className = "px-5 py-2 text-sm opacity-60";
  waiting.textContent = "Ranking…";
  ranked.replaceChildren(waiting);
  showRanking(true);
  htmx.ajax("GET", `/search?${params}`, { target: ranked, swap: "innerHTML" });
}

// Add `#tag` to the search box, or remove it if it's there, then filter.
function toggleTag(tag) {
  const input = document.getElementById("search");
  if (!input) return;
  const words = input.value.trim().split(/\s+/).filter(Boolean);
  const word = "#" + tag;
  const present = words.some((w) => w.toLowerCase() === word);
  const kept = present ? words.filter((w) => w.toLowerCase() !== word) : [...words, word];
  input.value = kept.join(" ");
  if (isRanking()) rank();
  else applySearch();
}

// Tag chips in the sidebar and tags in the note view; the ranking's close button.
document.addEventListener("click", (event) => {
  if (event.target.closest("[data-close-ranking]")) {
    showRanking(false);
    return;
  }
  const tag = event.target.closest("[data-tag]");
  if (!tag) return;
  event.preventDefault();
  toggleTag(tag.dataset.tag);
});

document.addEventListener("input", (event) => {
  if (event.target.id !== "search") return;
  showRanking(false);
  applySearch();
});
document.addEventListener("keydown", (event) => {
  if (event.target.id !== "search") return;
  if (event.key === "Enter" && !event.isComposing) {
    event.preventDefault();
    rank();
  } else if (event.key === "Escape") {
    event.target.value = "";
    showRanking(false);
    applySearch();
  }
});
// Re-apply the current search whenever the sidebar is (re)loaded.
htmx.onLoad(applySearch);

// Highlight the note whose page we're on (`/n/42`) in the sidebar.
function markCurrent() {
  const match = location.pathname.match(/^\/n\/(\d+)$/);
  const current = match ? match[1] : null;
  for (const item of document.querySelectorAll("#sidebar li[data-id]")) {
    item.querySelector("a").classList.toggle("menu-active", item.dataset.id === current);
  }
}

htmx.onLoad(markCurrent);
document.addEventListener("htmx:pushedIntoHistory", markCurrent);
// Back and forward restore an earlier page: bring its filter and highlight up to date.
document.addEventListener("htmx:historyRestore", () => {
  if (!document.getElementById("search")?.value.trim()) showRanking(false);
  applySearch();
  markCurrent();
});
