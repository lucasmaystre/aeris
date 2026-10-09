import re
import unicodedata

_WHITESPACE = re.compile(r"\s+")
_TAGS_LINE = re.compile(r"^\s*tags:(.*)$", re.IGNORECASE | re.MULTILINE)
_TAG = re.compile(r"#([^\W\d_][\w/-]*)")

TITLE_MAX_LENGTH = 80
_PLACEHOLDER_BASE = 0xE000  # Unicode private use area, for protecting escaped characters.
_ESCAPED = re.compile(r"\\([!-/:-@\[-`{-~])")
_PLACEHOLDER = re.compile("[\ue000-\uf8ff]")
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
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(c for c in decomposed if not unicodedata.category(c).startswith("M"))
    return _WHITESPACE.sub(" ", stripped.lower())


def extract_tags(content: str) -> list[str]:
    """Extract tags from the note's `Tags:` lines, e.g. `Tags: #aeris, #project/notes`.

    Only lines starting with `Tags:` (any case) count; a note may have several. A tag is `#`, a
    letter, then letters, digits, `_`, `-` or `/`. Tags are lowercased, deduplicated and sorted.
    """
    tags = {tag.lower() for line in _TAGS_LINE.findall(content) for tag in _TAG.findall(line)}
    return sorted(tags)


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


def _truncate(text: str) -> str:
    if len(text) <= TITLE_MAX_LENGTH:
        return text
    cut = text[: TITLE_MAX_LENGTH - 1]
    if text[TITLE_MAX_LENGTH - 1] != " " and " " in cut:
        cut = cut[: cut.rfind(" ")]
    return cut.rstrip() + "…"
