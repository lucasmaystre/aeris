"""Service layer: all note operations. Web and API routes are thin wrappers around these."""

from collections.abc import Sequence
from datetime import datetime
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from aeris_server.db import Note
from aeris_server.parsing import extract_tags, title

Order = Literal["created", "updated"]


class NoteData(BaseModel):
    """A note as returned to the web UI and the API."""

    id: int
    title: str
    tags: list[str]
    created_at: datetime
    updated_at: datetime
    content: str | None  # None when the caller asked for no content.
    deleted: bool


def get_note(session: Session, note_id: int) -> NoteData | None:
    """Return one note, or None if it doesn't exist or is deleted."""
    note = session.get(Note, note_id)
    if note is None or note.deleted:
        return None
    return _to_data(note)


def get_notes(session: Session, ids: Sequence[int]) -> list[NoteData]:
    """Return several notes in the requested order, skipping missing, deleted and repeated IDs."""
    unique = list(dict.fromkeys(ids))
    if not unique:
        return []
    notes = session.scalars(select(Note).where(Note.id.in_(unique), Note.deleted.is_(False)))
    by_id = {note.id: note for note in notes}
    return [_to_data(by_id[note_id]) for note_id in unique if note_id in by_id]


def list_notes(
    session: Session,
    *,
    order: Order = "created",
    since: datetime | None = None,
    tag: str | None = None,
    limit: int | None = None,
    content: bool = True,
) -> list[NoteData]:
    """List notes, newest first by creation or update time. Deleted notes are excluded.

    `since` filters on the same timestamp as `order`. `tag` also matches child tags: `project`
    matches `project/aeris`.
    """
    column = Note.created_at if order == "created" else Note.updated_at
    query = select(Note).where(Note.deleted.is_(False)).order_by(column.desc(), Note.id.desc())
    if since is not None:
        query = query.where(column >= since)
    if tag is not None:
        tag = tag.removeprefix("#").lower()
        element = func.unnest(Note.tags).column_valued("tag")
        query = query.where(
            select(element)
            .where(or_(element == tag, func.starts_with(element, tag + "/")))
            .exists()
        )
    if limit is not None:
        query = query.limit(limit)
    return [_to_data(note, content=content) for note in session.scalars(query)]


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


def _to_data(note: Note, *, content: bool = True) -> NoteData:
    return NoteData(
        id=note.id,
        title=title(note.content),
        tags=note.tags,
        created_at=note.created_at,
        updated_at=note.updated_at,
        content=note.content if content else None,
        deleted=note.deleted,
    )
