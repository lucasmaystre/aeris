"""JSON API for the CLI and agents. Thin wrappers around the service layer."""

from collections.abc import Iterator
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from aeris_server import notes
from aeris_server.auth import require_read
from aeris_server.db import get_session
from aeris_server.notes import NoteData, Order, SearchHit, TagCount

router = APIRouter(prefix="/api", dependencies=[Depends(require_read)])

SessionDep = Annotated[Session, Depends(get_session)]


class NoteList(BaseModel):
    notes: list[NoteData]
    missing: list[int]  # Requested IDs that don't exist or are deleted (batch fetch only).


class SearchResults(BaseModel):
    hits: list[SearchHit]


class TagList(BaseModel):
    tags: list[TagCount]


@router.get("/notes")
def list_notes(
    session: SessionDep,
    ids: Annotated[str | None, Query(pattern=r"^\d+(,\d+)*$")] = None,
    order: Order = "created",
    since: datetime | None = None,
    tag: str | None = None,
    limit: Annotated[int | None, Query(ge=1)] = None,
    content: bool = True,
) -> NoteList:
    """List notes newest first, or fetch several by ID (`ids=3,1,2`; other filters are ignored)."""
    if ids is not None:
        requested = [int(note_id) for note_id in ids.split(",")]
        found = notes.get_notes(session, requested, content=content)
        found_ids = {note.id for note in found}
        missing = [note_id for note_id in dict.fromkeys(requested) if note_id not in found_ids]
        return NoteList(notes=found, missing=missing)
    found = notes.list_notes(
        session, order=order, since=since, tag=tag, limit=limit, content=content
    )
    return NoteList(notes=found, missing=[])


@router.get("/notes/{note_id}")
def get_note(session: SessionDep, note_id: int) -> NoteData:
    note = notes.get_note(session, note_id)
    if note is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No note with id {note_id}.")
    return note


@router.get("/search")
def search(
    session: SessionDep,
    q: str,
    mode: Literal["text"] = "text",
    tag: str | None = None,
    limit: Annotated[int | None, Query(ge=1)] = None,
) -> SearchResults:
    """Substring search, ignoring case and accents. Semantic mode arrives in phase 4."""
    try:
        return SearchResults(hits=notes.search_notes(session, q, tag=tag, limit=limit))
    except notes.EmptyQuery as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error


@router.get("/tags")
def list_tags(session: SessionDep) -> TagList:
    return TagList(tags=notes.list_tags(session))


@router.get("/export")
def export(session: SessionDep) -> StreamingResponse:
    """Every note, including deleted ones, as JSON Lines."""
    exported = notes.export_notes(session)

    def lines() -> Iterator[str]:
        for note in exported:
            yield note.model_dump_json() + "\n"

    return StreamingResponse(lines(), media_type="application/x-ndjson")
