import re
import unicodedata

_WHITESPACE = re.compile(r"\s+")
_TAGS_LINE = re.compile(r"^\s*tags:(.*)$", re.IGNORECASE | re.MULTILINE)
_TAG = re.compile(r"#([^\W\d_][\w/-]*)")

TITLE_MAX_LENGTH = 80
PREVIEW_LENGTH = 140
SNIPPET_LENGTH = 160
_PLACEHOLDER_BASE = 0xE000  # Unicode private use area, for protecting escaped characters.
_ESCAPED = re.compile(r"\\([!-/:-@\[-`{-~])")
_PLACEHOLDER = re.compile("[\ue000-\uf8ff]")
_CODE_FENCE = re.compile(r"^\s*(```|~~~)")
_THEMATIC_BREAK = re.compile(r"^\s*([-*_])(\s*\1){2,}\s*$")
# Heading, blockquote, list item or task checkbox at the start of a line.
_BLOCK_MARKER = re.compile(r"^\s*(?:#{1,6}(?=\s|$)|>|[-*+](?=\s)|\d+[.)](?=\s)|\[[ xX]\](?=\s))")
_INLINE_MARKUP = [
    (re.compile(r"!?\[([^\]]*)\]\([^)]*\)"), r"\1"),  # Images and links.
    (re.compile(r"<([a-zA-Z][a-zA-Z0-9+.-]*:[^>\s]*)>"), r"\1"),  # Autolinks.
    (re.compile(r"(`+)(.+?)\1"), r"\2"),  # Code spans.
    (re.compile(r"\*\*(.+?)\*\*"), r"\1"),
    (re.compile(r"__(.+?)__"), r"\1"),
    (re.compile(r"~~(.+?)~~"), r"\1"),
    (re.compile(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])"), r"\1"),
    (re.compile(r"(?<!\w)_(?!\s)(.+?)(?<!\s)_(?!\w)"), r"\1"),
]


def normalize(text: str) -> str:
    """Normalize text for accent- and case-insensitive substring search.

    Mirrored in `app.js`: both sides must produce identical output, so change them together.

    Steps: decompose (NFKD), drop combining marks, lowercase, collapse whitespace runs to one space.
    Decomposing before lowercasing means `İ` becomes `i` rather than `i` plus a combining dot.
    """
    return _WHITESPACE.sub(" ", _strip_marks(text).lower())


def _strip_marks(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.category(c).startswith("M"))


def extract_tags(content: str) -> list[str]:
    """Extract tags from the note's `Tags:` lines, e.g. `Tags: #aeris, #project/notes`.

    Only lines starting with `Tags:` (any case) count; a note may have several. A tag is `#`, a
    letter, then letters, digits, `_`, `-` or `/`. Tags are lowercased, deduplicated and sorted.
    """
    tags = {tag.lower() for line in _TAGS_LINE.findall(content) for tag in _TAG.findall(line)}
    return sorted(tags)


def snippet(content: str, query: str) -> str:
    """Show the original text around the first match of `query`, about SNIPPET_LENGTH long.

    Matching uses `normalize`, so `ete` finds `Été`, but the snippet shows the original text. Without
    a match, shows the start of the content.
    """
    needle = normalize(query).strip()
    normalized, origins = _normalize_with_origins(content)
    index = normalized.find(needle) if needle else -1
    if index < 0:
        return _excerpt(content, 0, 0)
    return _excerpt(content, origins[index], origins[index + len(needle) - 1] + 1)


def _normalize_with_origins(text: str) -> tuple[str, list[int]]:
    """Like `normalize`, character by character, recording each output character's source index."""
    chars: list[str] = []
    origins: list[int] = []
    for i, original in enumerate(text):
        for char in _strip_marks(original).lower():
            if char.isspace():
                if chars and chars[-1] == " ":
                    continue
                char = " "
            chars.append(char)
            origins.append(i)
    return "".join(chars), origins


def _excerpt(content: str, start: int, end: int) -> str:
    """Cut a window of about SNIPPET_LENGTH around content[start:end], at word boundaries."""
    length = max(SNIPPET_LENGTH, end - start)
    lo = max(0, start - (length - (end - start)) // 2)
    hi = min(len(content), lo + length)
    lo = max(0, hi - length)
    if lo > 0 and (space := _WHITESPACE.search(content, lo, start)):
        lo = space.end()
    if hi < len(content) and (spaces := list(_WHITESPACE.finditer(content, end, hi))):
        hi = spaces[-1].start()
    text = _WHITESPACE.sub(" ", content[lo:hi]).strip()
    return ("…" if lo > 0 else "") + text + ("…" if hi < len(content) else "")


def title(content: str) -> str:
    """Compute a note's title: its first line with text, as plain text, truncated at a word.

    `Tags:` lines are skipped. Leading block markers (headings, quotes, list items) and inline
    markdown (emphasis, code, links) are removed. Returns "" if no line has any text.
    """
    for line in content.splitlines():
        if _TAGS_LINE.match(line):
            continue
        text = _clean_line(line)
        if text:
            return _truncate(text)
    return ""


def preview(content: str) -> str:
    """The text after a note's title, as plain text and cut at a word: what a list shows below it.

    Skips the title's line, `Tags:` lines and code fence markers.
    """
    texts: list[str] = []
    title_seen = False
    for line in content.splitlines():
        if _TAGS_LINE.match(line) or _CODE_FENCE.match(line):
            continue
        text = _clean_line(line)
        if not text:
            continue
        if title_seen:
            texts.append(text)
        title_seen = True
    return _truncate(" ".join(texts), PREVIEW_LENGTH)


def _clean_line(line: str) -> str:
    if _THEMATIC_BREAK.match(line):
        return ""
    # Protect escaped characters (e.g. `\*`) so they aren't treated as markup.
    escaped: list[str] = []

    def protect(match: re.Match[str]) -> str:
        escaped.append(match.group(1))
        return chr(_PLACEHOLDER_BASE + len(escaped) - 1)

    text = _ESCAPED.sub(protect, line)
    while (stripped := _BLOCK_MARKER.sub("", text, count=1)) != text:
        text = stripped
    for pattern, replacement in _INLINE_MARKUP:
        text = pattern.sub(replacement, text)

    def restore(match: re.Match[str]) -> str:
        index = ord(match.group()) - _PLACEHOLDER_BASE
        return escaped[index] if index < len(escaped) else match.group()

    text = _PLACEHOLDER.sub(restore, text)
    return _WHITESPACE.sub(" ", text).strip()


def _truncate(text: str, limit: int = TITLE_MAX_LENGTH) -> str:
    if len(text) <= limit:
        return text
    cut = text[: limit - 1]
    if text[limit - 1] != " " and " " in cut:
        cut = cut[: cut.rfind(" ")]
    return cut.rstrip() + "…"
