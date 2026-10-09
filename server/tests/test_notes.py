from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select

from aeris_server import db
from aeris_server.admin import main
from aeris_server.db import Note
from aeris_server.notes import get_note, get_notes, list_notes, recompute_tags

T0 = datetime(2026, 1, 1, tzinfo=UTC)


def _add(
    content: str,
    *,
    tags: list[str] | None = None,
    created: int = 0,
    updated: int | None = None,
    deleted: bool = False,
) -> int:
    """Insert a note directly; `created` and `updated` are days after T0."""
    with db.session() as session:
        note = Note(
            content=content,
            tags=tags or [],
            created_at=T0 + timedelta(days=created),
            updated_at=T0 + timedelta(days=created if updated is None else updated),
            deleted=deleted,
        )
        session.add(note)
        session.commit()
        return note.id


def _get(note_id: int) -> Note:
    with db.session() as session:
        note = session.get(Note, note_id)
        assert note is not None
        return note


# Reads.


@pytest.mark.usefixtures("database")
def test_get_note() -> None:
    note_id = _add("# Hello\n\nBody", tags=["a"])
    with db.session() as session:
        note = get_note(session, note_id)
    assert note is not None
    assert (note.id, note.title, note.tags, note.content) == (
        note_id,
        "Hello",
        ["a"],
        "# Hello\n\nBody",
    )
    assert note.created_at == T0
    assert not note.deleted


@pytest.mark.usefixtures("database")
def test_get_note_missing_or_deleted() -> None:
    deleted = _add("Gone", deleted=True)
    with db.session() as session:
        assert get_note(session, deleted) is None
        assert get_note(session, deleted + 1000) is None


@pytest.mark.usefixtures("database")
def test_get_notes() -> None:
    a, b = _add("A"), _add("B")
    deleted = _add("Gone", deleted=True)
    with db.session() as session:
        notes = get_notes(session, [b, deleted, a, b, 9999])
        assert [n.id for n in notes] == [b, a]
        assert get_notes(session, []) == []


def _ids(**kwargs: Any) -> list[int]:
    with db.session() as session:
        return [note.id for note in list_notes(session, **kwargs)]


@pytest.mark.usefixtures("database")
def test_list_notes_order_and_since() -> None:
    old = _add("Old, recently edited", created=0, updated=5)
    mid = _add("Mid", created=2)
    new = _add("New", created=4)
    _add("Deleted", created=6, deleted=True)

    assert _ids() == [new, mid, old]
    assert _ids(order="updated") == [old, new, mid]
    assert _ids(since=T0 + timedelta(days=2)) == [new, mid]
    assert _ids(order="updated", since=T0 + timedelta(days=5)) == [old]
    assert _ids(limit=2) == [new, mid]


@pytest.mark.usefixtures("database")
def test_list_notes_by_tag() -> None:
    parent = _add("Parent", tags=["project"], created=0)
    child = _add("Child", tags=["notes", "project/aeris"], created=1)
    _add("Similar", tags=["projects"], created=2)
    _add("Untagged", created=3)

    assert _ids(tag="project") == [child, parent]
    assert _ids(tag="#Project") == [child, parent]
    assert _ids(tag="project/aeris") == [child]
    assert _ids(tag="notes") == [child]
    assert _ids(tag="missing") == []


@pytest.mark.usefixtures("database")
def test_list_notes_without_content() -> None:
    _add("# Title\n\nBody")
    with db.session() as session:
        [note] = list_notes(session, content=False)
    assert note.content is None
    assert note.title == "Title"


# Tags backfill.


@pytest.mark.usefixtures("database")
def test_recompute_tags() -> None:
    tagged = _add("Title\nTags: #b, #a")
    stale = _add("No tag line any more", tags=["old"])
    untagged = _add("Plain note")
    before = _get(tagged).updated_at

    with db.session() as session:
        assert recompute_tags(session) == 2

    assert _get(tagged).tags == ["a", "b"]
    assert _get(tagged).updated_at == before
    assert _get(stale).tags == []
    assert _get(untagged).tags == []
    with db.session() as session:
        assert recompute_tags(session) == 0
        assert session.scalars(select(db.NoteRevision)).all() == []


@pytest.mark.usefixtures("database")
def test_admin_recompute_tags(capsys: pytest.CaptureFixture[str]) -> None:
    _add("Tags: #x")
    main(["recompute-tags"])
    assert capsys.readouterr().out == "Updated 1 note.\n"
