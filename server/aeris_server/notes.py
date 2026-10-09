"""Service layer: all note operations. Web and API routes are thin wrappers around these."""

from collections.abc import Sequence
from datetime import datetime
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import InstrumentedAttribute, Session

from aeris_server.db import Note, NoteRevision
from aeris_server.parsing import extract_tags, normalize, snippet, title

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


class SearchHit(BaseModel):
    """A search result: enough to pick notes, without their full content."""

    id: int
    title: str
    tags: list[str]
    created_at: datetime
    updated_at: datetime
    snippet: str
    score: float | None  # Semantic search only.


class NoteNotFound(Exception):
    def __init__(self, note_id: int) -> None:
        super().__init__(f"No note with id {note_id}.")
        self.note_id = note_id


class EmptyContent(ValueError):
    def __init__(self) -> None:
        super().__init__("Note content cannot be empty.")


class EmptyQuery(ValueError):
    def __init__(self) -> None:
        super().__init__("Search query cannot be empty.")


class StaleNote(Exception):
    """The note changed since the caller loaded it. `current` is its latest version."""

    def __init__(self, current: NoteData) -> None:
        super().__init__(f"Note {current.id} was changed at {current.updated_at.isoformat()}.")
        self.current = current


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
    query = _live_notes(order, tag)
    if since is not None:
        query = query.where(_timestamp(order) >= since)
    if limit is not None:
        query = query.limit(limit)
    return [_to_data(note, content=content) for note in session.scalars(query)]


def search_notes(
    session: Session, query: str, *, tag: str | None = None, limit: int | None = None
) -> list[SearchHit]:
    """Find notes containing `query` as a phrase, ignoring case, accents and whitespace runs.

    Newest first. Matches the web UI's in-browser search exactly, since both use `normalize`.
    """
    needle = normalize(query).strip()
    if not needle:
        raise EmptyQuery()
    hits: list[SearchHit] = []
    for note in session.scalars(_live_notes("created", tag)):
        if limit is not None and len(hits) >= limit:
            break
        if needle in normalize(note.content):
            hits.append(
                SearchHit(
                    id=note.id,
                    title=title(note.content),
                    tags=note.tags,
                    created_at=note.created_at,
                    updated_at=note.updated_at,
                    snippet=snippet(note.content, query),
                    score=None,
                )
            )
    return hits


def create_note(session: Session, content: str) -> NoteData:
    content = _clean(content)
    note = Note(content=content, tags=extract_tags(content))
    session.add(note)
    session.commit()
    return _to_data(note)


def update_note(
    session: Session, note_id: int, content: str, expected_updated_at: datetime | None = None
) -> NoteData:
    """Replace a note's content, keeping the old content as a revision.

    If `expected_updated_at` is given and the note has changed since, raises `StaleNote`. Saving
    unchanged content does nothing.
    """
    content = _clean(content)
    note = _lock(session, note_id)
    if expected_updated_at is not None and note.updated_at != expected_updated_at:
        current = _to_data(note)
        session.rollback()
        raise StaleNote(current)
    if content == note.content:
        unchanged = _to_data(note)
        session.rollback()
        return unchanged
    _replace(session, note, content)
    return _to_data(note)


def append_note(session: Session, note_id: int, text: str) -> NoteData:
    """Add text to the end of a note, as a new paragraph. Never conflicts."""
    text = _clean(text)
    note = _lock(session, note_id)
    _replace(session, note, f"{note.content.rstrip()}\n\n{text}")
    return _to_data(note)


def delete_note(session: Session, note_id: int) -> None:
    """Soft-delete a note."""
    note = _lock(session, note_id)
    note.deleted = True
    session.commit()


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


def _timestamp(order: Order) -> InstrumentedAttribute[datetime]:
    return Note.created_at if order == "created" else Note.updated_at


def _live_notes(order: Order, tag: str | None) -> Select[tuple[Note]]:
    """Non-deleted notes, newest first, optionally with a tag or one of its children."""
    timestamp = _timestamp(order)
    query = select(Note).where(Note.deleted.is_(False)).order_by(timestamp.desc(), Note.id.desc())
    if tag is not None:
        tag = tag.removeprefix("#").lower()
        element = func.unnest(Note.tags).column_valued("tag")
        query = query.where(
            select(element)
            .where(or_(element == tag, func.starts_with(element, tag + "/")))
            .exists()
        )
    return query


def _clean(content: str) -> str:
    content = content.strip()
    if not content:
        raise EmptyContent()
    return content


def _lock(session: Session, note_id: int) -> Note:
    """Load a live note and lock its row until the transaction ends."""
    query = select(Note).where(Note.id == note_id).with_for_update()
    note = session.scalars(query.execution_options(populate_existing=True)).one_or_none()
    if note is None or note.deleted:
        session.rollback()
        raise NoteNotFound(note_id)
    return note


def _replace(session: Session, note: Note, content: str) -> None:
    session.add(NoteRevision(note_id=note.id, content=note.content))
    note.content = content
    note.tags = extract_tags(content)
    note.updated_at = func.now()
    session.commit()


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
