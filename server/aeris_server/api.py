"""JSON API for the CLI and agents. Thin wrappers around the service layer."""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from aeris_server import notes
from aeris_server.auth import require_read, require_write
from aeris_server.db import get_session
from aeris_server.embeddings import EmbeddingError
from aeris_server.notes import NoteData, Order, SearchHit, TagCount

router = APIRouter(prefix="/api", dependencies=[Depends(require_read)])

SessionDep = Annotated[Session, Depends(get_session)]
WRITE = [Depends(require_write)]


class NoteList(BaseModel):
    notes: list[NoteData]
    missing: list[int]  # Requested IDs that don't exist or are deleted (batch fetch only).


class SearchResults(BaseModel):
    hits: list[SearchHit]


class TagList(BaseModel):
    tags: list[TagCount]


class NewNote(BaseModel):
    content: str


class NoteEdit(BaseModel):
    content: str
    expected_updated_at: datetime | None = None  # Rejects the edit (409) if the note changed since.


@contextmanager
def _service_errors() -> Iterator[None]:
    """Turn service-layer errors into HTTP errors."""
    try:
        yield
    except notes.NoteNotFound as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
    except (notes.EmptyContent, notes.EmptyQuery) as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error
    except EmbeddingError as error:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(error)) from error


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
    mode: Literal["text", "semantic"] = "text",
    tag: str | None = None,
    limit: Annotated[int | None, Query(ge=1)] = None,
) -> SearchResults:
    """`text`: notes containing `q`, ignoring case and accents, newest first. `semantic`: the notes
    closest in meaning, best first, with a score (10 unless `limit` says otherwise)."""
    with _service_errors():
        if mode == "semantic":
            limit = limit or notes.SEMANTIC_LIMIT
            tags = [tag] if tag else []
            return SearchResults(hits=notes.semantic_search(session, q, tags=tags, limit=limit))
        return SearchResults(hits=notes.search_notes(session, q, tag=tag, limit=limit))


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


@router.post("/notes", dependencies=WRITE, status_code=status.HTTP_201_CREATED)
def create_note(session: SessionDep, body: NewNote, response: Response) -> NoteData:
    with _service_errors():
        note = notes.create_note(session, body.content)
    response.headers["Location"] = f"/api/notes/{note.id}"
    return note


@router.put("/notes/{note_id}", dependencies=WRITE, response_model=NoteData)
def update_note(session: SessionDep, note_id: int, body: NoteEdit) -> NoteData | JSONResponse:
    """Replace a note's content. A stale `expected_updated_at` gives 409 with the `current` note."""
    with _service_errors():
        try:
            return notes.update_note(session, note_id, body.content, body.expected_updated_at)
        except notes.StaleNote as error:
            return JSONResponse(
                {"detail": str(error), "current": error.current.model_dump(mode="json")},
                status_code=status.HTTP_409_CONFLICT,
            )


@router.delete("/notes/{note_id}", dependencies=WRITE, status_code=status.HTTP_204_NO_CONTENT)
def delete_note(session: SessionDep, note_id: int) -> None:
    with _service_errors():
        notes.delete_note(session, note_id)
