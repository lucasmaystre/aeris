"""Embedding notes on write, and reindexing. OpenRouter is replaced by a fake embedder."""

import hashlib

import pytest
from sqlalchemy import select

from aeris_server import db, embeddings
from aeris_server.admin import main
from aeris_server.db import Note, NoteEmbedding
from aeris_server.embeddings import EmbeddingError
from aeris_server.notes import append_note, create_note, reindex, update_note

MODEL = "fake/model"


class FakeEmbedder:
    """Records each request's texts; vectors encode the text's length.

    Fails every request once `fail_after` requests have succeeded (0: fail from the start).
    """

    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.fail_after: int | None = None

    def __call__(self, texts: list[str], **_: object) -> list[list[float]]:
        if self.fail_after is not None and len(self.calls) >= self.fail_after:
            raise EmbeddingError("OpenRouter returned 500.")
        self.calls.append(texts)
        return [[float(len(text)), 1.0] for text in texts]


@pytest.fixture
def embedder(monkeypatch: pytest.MonkeyPatch) -> FakeEmbedder:
    fake = FakeEmbedder()
    monkeypatch.setattr(embeddings, "embed", fake)
    monkeypatch.setenv(embeddings.MODEL_VAR, MODEL)
    return fake


def _add(content: str, *, deleted: bool = False) -> int:
    """Insert a note directly, with no embedding."""
    with db.session() as session:
        note = Note(content=content, tags=[], deleted=deleted)
        session.add(note)
        session.commit()
        return note.id


def _stored(note_id: int) -> tuple[str, str, list[float]] | None:
    with db.session() as session:
        row = session.get(NoteEmbedding, note_id)
        return None if row is None else (row.model, row.content_hash, list(row.embedding))


def _sha(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()


# On write.


@pytest.mark.usefixtures("database")
def test_create_embeds(embedder: FakeEmbedder) -> None:
    with db.session() as session:
        note = create_note(session, "  Hello  ")
    assert embedder.calls == [["Hello"]]
    assert _stored(note.id) == (MODEL, _sha("Hello"), [5.0, 1.0])


@pytest.mark.usefixtures("database")
def test_update_and_append_reembed(embedder: FakeEmbedder) -> None:
    with db.session() as session:
        note = create_note(session, "One")
        update_note(session, note.id, "Two!")
        append_note(session, note.id, "Three")
    assert embedder.calls == [["One"], ["Two!"], ["Two!\n\nThree"]]
    assert _stored(note.id) == (MODEL, _sha("Two!\n\nThree"), [11.0, 1.0])


@pytest.mark.usefixtures("database")
def test_unchanged_update_doesnt_embed(embedder: FakeEmbedder) -> None:
    with db.session() as session:
        note = create_note(session, "Same")
        update_note(session, note.id, "Same")
    assert embedder.calls == [["Same"]]


@pytest.mark.usefixtures("database")
def test_embedding_failure_still_saves(
    embedder: FakeEmbedder, caplog: pytest.LogCaptureFixture
) -> None:
    embedder.fail_after = 0
    with db.session() as session:
        note = create_note(session, "Saved anyway")
        updated = update_note(session, note.id, "Still saved")
    assert updated.content == "Still saved"
    assert _stored(note.id) is None
    assert f"Couldn't embed note {note.id}: OpenRouter returned 500." in caplog.text


@pytest.mark.usefixtures("database")
def test_without_a_key_notes_still_save() -> None:
    # The autouse `_no_openrouter` fixture removes the key, as on a server without one.
    with db.session() as session:
        note = create_note(session, "No key")
    assert _stored(note.id) is None


# Reindex.


@pytest.mark.usefixtures("database")
def test_reindex_embeds_missing_and_stale(
    embedder: FakeEmbedder, monkeypatch: pytest.MonkeyPatch
) -> None:
    with db.session() as session:
        fresh = create_note(session, "Fresh").id
        edited = create_note(session, "Before").id
        other_model = create_note(session, "Old model").id
    missing = _add("Missing")
    _add("Deleted", deleted=True)
    with db.session() as session:
        session.get_one(Note, edited).content = "After"
        session.get_one(NoteEmbedding, other_model).model = "old/model"
        session.commit()
    embedder.calls.clear()

    with db.session() as session:
        result = reindex(session)

    assert (result.embedded, result.up_to_date) == (3, 1)
    assert embedder.calls == [["After", "Old model", "Missing"]]
    assert _stored(edited) == (MODEL, _sha("After"), [5.0, 1.0])
    assert _stored(other_model) == (MODEL, _sha("Old model"), [9.0, 1.0])
    assert _stored(missing) == (MODEL, _sha("Missing"), [7.0, 1.0])
    assert _stored(fresh) == (MODEL, _sha("Fresh"), [5.0, 1.0])
    with db.session() as session:
        assert reindex(session).embedded == 0


@pytest.mark.usefixtures("database")
def test_reindex_batches_and_resumes(embedder: FakeEmbedder) -> None:
    ids = [_add(f"Note {n}") for n in range(5)]
    embedder.fail_after = 1
    with db.session() as session, pytest.raises(EmbeddingError):
        reindex(session, batch_size=2)
    assert [_stored(note_id) is not None for note_id in ids] == [True, True, False, False, False]

    embedder.fail_after = None
    with db.session() as session:
        result = reindex(session, batch_size=2)
    assert (result.embedded, result.up_to_date) == (3, 2)
    assert embedder.calls == [["Note 0", "Note 1"], ["Note 2", "Note 3"], ["Note 4"]]


@pytest.mark.usefixtures("database")
def test_admin_reindex(embedder: FakeEmbedder, capsys: pytest.CaptureFixture[str]) -> None:
    _add("Only note")
    main(["reindex"])
    assert capsys.readouterr().out == "Embedded 1 note (0 already up to date).\n"
    main(["reindex"])
    assert capsys.readouterr().out == "Embedded 0 notes (1 already up to date).\n"


@pytest.mark.usefixtures("database")
def test_admin_reindex_failure(embedder: FakeEmbedder) -> None:
    _add("Only note")
    embedder.fail_after = 0
    with pytest.raises(SystemExit, match="Reindex failed, run it again to resume: .*500"):
        main(["reindex"])
    with db.session() as session:
        assert session.scalars(select(NoteEmbedding)).all() == []
