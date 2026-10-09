import pytest
from sqlalchemy import select

from aeris_server import db
from aeris_server.admin import main
from aeris_server.db import Note
from aeris_server.notes import recompute_tags


def _add(content: str, tags: list[str] | None = None) -> int:
    with db.session() as session:
        note = Note(content=content, tags=tags or [])
        session.add(note)
        session.commit()
        return note.id


def _get(note_id: int) -> Note:
    with db.session() as session:
        note = session.get(Note, note_id)
        assert note is not None
        return note


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
