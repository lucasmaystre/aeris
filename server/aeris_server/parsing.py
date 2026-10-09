import re
import unicodedata

_WHITESPACE = re.compile(r"\s+")


def normalize(text: str) -> str:
    """Normalize text for accent- and case-insensitive substring search.

    Mirrored in `app.js`: both sides must produce identical output, so change them together.

    Steps: decompose (NFKD), drop combining marks, lowercase, collapse whitespace runs to one space.
    Decomposing before lowercasing means `İ` becomes `i` rather than `i` plus a combining dot.
    """
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(c for c in decomposed if not unicodedata.category(c).startswith("M"))
    return _WHITESPACE.sub(" ", stripped.lower())
