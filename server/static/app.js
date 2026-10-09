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
// mirror `normalize` in server/aeris_server/parsing.py: change them together.

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

function applySearch() {
  const input = document.getElementById("search");
  const list = document.getElementById("note-list");
  if (!input || !list) return;
  const query = normalize(input.value).trim();
  let shown = 0;
  for (const item of list.querySelectorAll("li[data-text]")) {
    let entry = searchIndex.get(item);
    if (!entry) {
      entry = indexText(item.dataset.text);
      searchIndex.set(item, entry);
    }
    const at = query ? entry.normalized.indexOf(query) : -1;
    const matches = !query || at >= 0;
    item.hidden = !matches;
    if (matches) shown++;
    const preview = item.querySelector(".preview");
    const snippet = item.querySelector(".snippet");
    if (preview) preview.hidden = at >= 0;
    snippet.hidden = at < 0;
    if (at >= 0) snippet.replaceChildren(...snippetNodes(entry, at, query.length));
  }
  const noMatches = list.querySelector(".no-matches");
  if (noMatches) noMatches.hidden = !query || shown > 0;
}

document.addEventListener("input", (event) => {
  if (event.target.id === "search") applySearch();
});
document.addEventListener("keydown", (event) => {
  if (event.target.id === "search" && event.key === "Escape") {
    event.target.value = "";
    applySearch();
  }
});
// Re-apply the current search whenever the sidebar is (re)loaded.
htmx.onLoad(applySearch);
