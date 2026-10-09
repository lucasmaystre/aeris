from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select

from aeris_server import db
from aeris_server.admin import main
from aeris_server.db import Note, NoteRevision
from aeris_server.notes import (
    EmptyContent,
    EmptyQuery,
    NoteNotFound,
    StaleNote,
    append_note,
    create_note,
    delete_note,
    export_notes,
    get_note,
    get_notes,
    list_notes,
    list_tags,
    recompute_tags,
    search_notes,
    update_note,
)

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


# Tags and export.


@pytest.mark.usefixtures("database")
def test_list_tags() -> None:
    _add("A", tags=["work", "project/aeris"])
    _add("B", tags=["project", "work"])
    _add("C", tags=["work"])
    _add("Gone", tags=["secret", "work"], deleted=True)
    with db.session() as session:
        tags = [(t.tag, t.count) for t in list_tags(session)]
    assert tags == [("project", 1), ("project/aeris", 1), ("work", 3)]


@pytest.mark.usefixtures("database")
def test_list_tags_empty() -> None:
    _add("Untagged")
    with db.session() as session:
        assert list_tags(session) == []


@pytest.mark.usefixtures("database")
def test_export_notes() -> None:
    first = _add("First", created=5)
    gone = _add("Gone", deleted=True)
    with db.session() as session:
        notes = export_notes(session)
    assert [(n.id, n.content, n.deleted) for n in notes] == [
        (first, "First", False),
        (gone, "Gone", True),
    ]


# Search.


def _search(query: str, **kwargs: Any) -> list[int]:
    with db.session() as session:
        return [hit.id for hit in search_notes(session, query, **kwargs)]


@pytest.mark.usefixtures("database")
def test_search_notes() -> None:
    older = _add("Notes on DISTRIBUTED\n  systems", created=0)
    newer = _add("Un été: distributed systems again", tags=["work"], created=1)
    _add("Distributed, but not that kind of systems", created=2)
    _add("distributed systems, deleted", created=3, deleted=True)

    assert _search("distributed systems") == [newer, older]
    assert _search("  Distributed   Systems ") == [newer, older]
    assert _search("ETE") == [newer]
    assert _search("distributed systems", tag="work") == [newer]
    assert _search("distributed systems", limit=1) == [newer]
    assert _search("absent") == []


@pytest.mark.usefixtures("database")
def test_search_hit_shape() -> None:
    note_id = _add("# Trip\n\nWe went to the sea in été.", tags=["travel"])
    with db.session() as session:
        [hit] = search_notes(session, "ete")
    assert (hit.id, hit.title, hit.tags) == (note_id, "Trip", ["travel"])
    assert hit.snippet == "# Trip We went to the sea in été."
    assert hit.score is None


@pytest.mark.usefixtures("database")
def test_search_empty_query() -> None:
    with db.session() as session, pytest.raises(EmptyQuery):
        search_notes(session, " \u0301 ")


# Writes.


def _revisions(note_id: int) -> list[str]:
    with db.session() as session:
        query = select(NoteRevision.content).where(NoteRevision.note_id == note_id)
        return list(session.scalars(query.order_by(NoteRevision.id)))


@pytest.mark.usefixtures("database")
def test_create_note() -> None:
    with db.session() as session:
        note = create_note(session, "\n  # Plan\n\nTags: #b, #a\n  ")
    assert (note.title, note.tags, note.content) == ("Plan", ["a", "b"], "# Plan\n\nTags: #b, #a")
    assert note.created_at == note.updated_at
    with db.session() as session:
        assert get_note(session, note.id) == note


@pytest.mark.usefixtures("database")
def test_create_note_empty() -> None:
    with db.session() as session, pytest.raises(EmptyContent):
        create_note(session, " \n ")


@pytest.mark.usefixtures("database")
def test_update_note() -> None:
    note_id = _add("Old")
    with db.session() as session:
        note = update_note(session, note_id, "New\nTags: #x", expected_updated_at=T0)
    assert (note.content, note.tags) == ("New\nTags: #x", ["x"])
    assert note.updated_at > T0
    assert note.created_at == T0
    assert _revisions(note_id) == ["Old"]


@pytest.mark.usefixtures("database")
def test_update_note_unchanged() -> None:
    note_id = _add("Same")
    with db.session() as session:
        note = update_note(session, note_id, "  Same\n")
    assert note.updated_at == T0
    assert _revisions(note_id) == []


@pytest.mark.usefixtures("database")
def test_update_note_stale() -> None:
    note_id = _add("Old", updated=3)
    with db.session() as session, pytest.raises(StaleNote) as error:
        update_note(session, note_id, "New", expected_updated_at=T0)
    assert error.value.current.content == "Old"
    assert error.value.current.updated_at == T0 + timedelta(days=3)
    assert _get(note_id).content == "Old"


@pytest.mark.usefixtures("database")
def test_update_note_errors() -> None:
    deleted = _add("Gone", deleted=True)
    with db.session() as session:
        with pytest.raises(NoteNotFound):
            update_note(session, deleted, "New")
        with pytest.raises(NoteNotFound):
            update_note(session, 9999, "New")
        with pytest.raises(EmptyContent):
            update_note(session, _add("Live"), "  ")


@pytest.mark.usefixtures("database")
def test_append_note() -> None:
    note_id = _add("Start\n")
    with db.session() as session:
        note = append_note(session, note_id, "\nMore\nTags: #added\n")
    assert note.content == "Start\n\nMore\nTags: #added"
    assert note.tags == ["added"]
    assert note.updated_at > T0
    assert _revisions(note_id) == ["Start\n"]


@pytest.mark.usefixtures("database")
def test_append_note_errors() -> None:
    with db.session() as session:
        with pytest.raises(NoteNotFound):
            append_note(session, 9999, "More")
        with pytest.raises(EmptyContent):
            append_note(session, _add("Live"), "")


@pytest.mark.usefixtures("database")
def test_delete_note() -> None:
    note_id = _add("Doomed")
    with db.session() as session:
        delete_note(session, note_id)
        assert get_note(session, note_id) is None
        assert list_notes(session) == []
        with pytest.raises(NoteNotFound):
            delete_note(session, note_id)
    assert _get(note_id).updated_at == T0


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
        assert session.scalars(select(NoteRevision)).all() == []


@pytest.mark.usefixtures("database")
def test_admin_recompute_tags(capsys: pytest.CaptureFixture[str]) -> None:
    _add("Tags: #x")
    main(["recompute-tags"])
    assert capsys.readouterr().out == "Updated 1 note.\n"
