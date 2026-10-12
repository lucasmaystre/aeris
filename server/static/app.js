// aeris: small browser-side behaviour, loaded on every page after htmx. Sections: times, search,
// ranking, tags, the current note; all event handling is wired up at the end.

// --- Times -------------------------------------------------------------------------------------
// The server renders <time datetime="..."> in UTC, or as "3 minutes ago" (`data-ago`); here they
// show in the viewer's timezone, with the full date as a tooltip.

const AGO_UNITS = [
  ["year", 365 * 86400],
  ["month", 30 * 86400],
  ["day", 86400],
  ["hour", 3600],
  ["minute", 60],
];

function fullDate(moment) {
  return moment.toLocaleString(undefined, {
    weekday: "long", year: "numeric", month: "long", day: "numeric",
    hour: "2-digit", minute: "2-digit", timeZoneName: "short",
  });
}

// The same wording as `ago` in server/aeris_server/web.py: change them together.
function ago(moment) {
  const seconds = (Date.now() - moment.getTime()) / 1000;
  for (const [unit, size] of AGO_UNITS) {
    if (seconds >= size) {
      const count = Math.floor(seconds / size);
      return `${count} ${unit}${count === 1 ? "" : "s"} ago`;
    }
  }
  return "just now";
}

// "2026-10-09 19:59" for absolute times; "3 minutes ago" (refreshed every minute) for relative ones.
function showTimes(root) {
  const pad = (number) => String(number).padStart(2, "0");
  for (const element of root.querySelectorAll("time[datetime]")) {
    const moment = new Date(element.getAttribute("datetime"));
    if (Number.isNaN(moment.getTime())) continue;
    element.textContent = element.hasAttribute("data-ago")
      ? ago(moment)
      : `${moment.getFullYear()}-${pad(moment.getMonth() + 1)}-${pad(moment.getDate())} ` +
        `${pad(moment.getHours())}:${pad(moment.getMinutes())}`;
    element.title = fullDate(moment);
  }
}

// --- Search ------------------------------------------------------------------------------------
// Filter the sidebar as you type, ignoring case, accents and whitespace runs. The steps mirror
// `normalize` in server/aeris_server/parsing.py: change them together. Words starting with `#`
// filter by tag instead, like the server's tag filter: `#project` matches `project/aeris`.

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
  mark.className = "bg-primary/20 text-base-content rounded-sm";
  mark.textContent = flat(text.slice(from, end)).trim();
  return [
    (low > 0 ? "…" : "") + flat(text.slice(low, from)).trimStart(),
    mark,
    flat(text.slice(end, high)).trimEnd() + (high < text.length ? "…" : ""),
  ];
}

const isTagWord = (word) => word.startsWith("#") && word.length > 1;

// Split the search box into tag filters (`#word`, lowercased) and the phrase: as typed (`text`)
// and normalized (`phrase`).
function parseQuery(value) {
  const words = value.trim().split(/\s+/).filter(Boolean);
  const text = words.filter((word) => !isTagWord(word)).join(" ");
  return {
    tags: words.filter(isTagWord).map((word) => word.slice(1).toLowerCase()),
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

// Empty the search box and show the whole list.
function clearSearch() {
  const input = document.getElementById("search");
  if (input) input.value = "";
  showRanking(false);
  applySearch();
}

// --- Ranking -----------------------------------------------------------------------------------
// Enter ranks notes by semantic similarity to the phrase (the server embeds it, so it takes about a
// second). The results stand in for the list; typing goes back to filtering.

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
  waiting.className = "px-4 py-2 text-sm opacity-60";
  waiting.textContent = "Ranking…";
  ranked.replaceChildren(waiting);
  showRanking(true);
  htmx.ajax("GET", `/search?${params}`, { target: ranked });
}

// --- Tags --------------------------------------------------------------------------------------
// Clicking a tag on an open note adds `#tag` to the search box, or removes it, then searches again.

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

// --- The current note --------------------------------------------------------------------------
// Mark the note whose page we're on (`/n/42`) in the sidebar, for styling and screen readers; none
// while writing a new note there (the URL stays, so Cancel brings the note back).

function markCurrent() {
  const match = location.pathname.match(/^\/n\/(\d+)$/);
  const creating = document.querySelector("#main-panel [data-new-note]");
  const current = match && !creating ? match[1] : null;
  for (const item of document.querySelectorAll("#sidebar li[data-id]")) {
    const link = item.querySelector("a");
    if (item.dataset.id === current) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  }
}

// --- Events ------------------------------------------------------------------------------------

// On the initial page and every fragment htmx swaps in (the sidebar, a note, ranked results).
htmx.onLoad((root) => {
  showTimes(root);
  applySearch();
  markCurrent();
});
setInterval(() => showTimes(document), 60_000);

document.addEventListener("input", (event) => {
  if (event.target.id === "search") {
    showRanking(false);
    applySearch();
  }
});

document.addEventListener("keydown", (event) => {
  // In the search box: Enter ranks, Escape clears.
  if (event.target.id === "search") {
    if (event.key === "Enter" && !event.isComposing) {
      event.preventDefault();
      rank();
    } else if (event.key === "Escape") {
      clearSearch();
    }
    return;
  }
  // `/` anywhere but in a text field jumps to the search box.
  if (event.key !== "/" || event.metaKey || event.ctrlKey || event.altKey) return;
  if (event.target.closest("input, textarea, select, [contenteditable]")) return;
  const input = document.getElementById("search");
  if (!input) return;
  event.preventDefault();
  input.focus();
  input.select();
});

document.addEventListener("click", (event) => {
  if (event.target.closest("[data-close-ranking]")) {
    showRanking(false);
    return;
  }
  const tag = event.target.closest("[data-tag]");
  if (tag) {
    event.preventDefault();
    toggleTag(tag.dataset.tag);
  }
});

// After creating a note, show the whole list so the new note appears (and is selected). The
// server's `HX-Trigger: noteCreated` also reloads the list.
document.addEventListener("noteCreated", clearSearch);

document.addEventListener("htmx:pushedIntoHistory", markCurrent);

// htmx's history snapshot is the page's HTML, which has no typed values: put the search box's in.
document.addEventListener("htmx:beforeHistorySave", () => {
  const input = document.getElementById("search");
  if (input) input.setAttribute("value", input.value);
});

// Back and forward restore an earlier page: bring its filter and highlight up to date.
document.addEventListener("htmx:historyRestore", () => {
  if (!document.getElementById("search")?.value.trim()) showRanking(false);
  applySearch();
  markCurrent();
});
