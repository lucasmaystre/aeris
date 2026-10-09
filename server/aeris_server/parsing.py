import re
import unicodedata

_WHITESPACE = re.compile(r"\s+")
_TAGS_LINE = re.compile(r"^\s*tags:(.*)$", re.IGNORECASE | re.MULTILINE)
_TAG = re.compile(r"#([^\W\d_][\w/-]*)")


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
