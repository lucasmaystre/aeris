"""Service layer: all note operations. Web and API routes are thin wrappers around these."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from aeris_server.db import Note
from aeris_server.parsing import extract_tags


def recompute_tags(session: Session) -> int:
    """Recompute every note's tags from its content. Returns the number of notes changed.

    Doesn't touch `updated_at` or create revisions: tags are derived, not edited.
    """
    changed = 0
    for note in session.scalars(select(Note)):
        tags = extract_tags(note.content)
        if note.tags != tags:
            note.tags = tags
            changed += 1
    session.commit()
    return changed
