"""Embedding notes on write, reindexing and semantic search. OpenRouter is replaced by a fake."""

import hashlib

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from aeris_server import db, embeddings
from aeris_server.admin import main
from aeris_server.app import app
from aeris_server.db import Note, NoteEmbedding
from aeris_server.embeddings import EmbeddingError
from aeris_server.notes import (
    EmptyQuery,
    create_note,
    delete_note,
    reindex,
    semantic_search,
    update_note,
)
from aeris_server.web import RANKING_UNAVAILABLE

MODEL = "fake/model"


class FakeEmbedder:
    """Records each request's texts. Vectors come from `vectors`, else encode the text's length.

    Fails every request once `fail_after` requests have succeeded (0: fail from the start).
    """

    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.vectors: dict[str, list[float]] = {}
        self.fail_after: int | None = None

    def __call__(self, texts: list[str], **_: object) -> list[list[float]]:
        if self.fail_after is not None and len(self.calls) >= self.fail_after:
            raise EmbeddingError("OpenRouter returned 500.")
        self.calls.append(texts)
        return [self.vectors.get(text, [float(len(text)), 1.0]) for text in texts]


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
def test_update_reembeds(embedder: FakeEmbedder) -> None:
    with db.session() as session:
        note = create_note(session, "One")
        update_note(session, note.id, "Two!")
    assert embedder.calls == [["One"], ["Two!"]]
    assert _stored(note.id) == (MODEL, _sha("Two!"), [4.0, 1.0])


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


# Semantic search.

CATS = "Cats\nThey purr."
DOGS = "Dogs\nThey bark.\nTags: #pets"
TAXES = "Taxes\nForms to file.\nTags: #admin"


@pytest.fixture
def pets(embedder: FakeEmbedder) -> dict[str, int]:
    """Three notes at known angles from the query `felines`: 0, about 37 and 90 degrees."""
    embedder.vectors = {
        CATS: [1.0, 0.0],
        DOGS: [0.8, 0.6],
        TAXES: [0.0, 1.0],
        "felines": [1.0, 0.0],
    }
    with db.session() as session:
        return {
            name: create_note(session, content).id
            for name, content in [("cats", CATS), ("dogs", DOGS), ("taxes", TAXES)]
        }


def _ranked(*, tags: list[str] | None = None, limit: int = 10) -> list[tuple[int, float]]:
    with db.session() as session:
        hits = semantic_search(session, "felines", tags=tags or [], limit=limit)
    return [(hit.id, round(hit.score or 0, 4)) for hit in hits]


@pytest.mark.usefixtures("database")
def test_semantic_search_ranks_by_similarity(pets: dict[str, int]) -> None:
    assert _ranked() == [(pets["cats"], 1.0), (pets["dogs"], 0.8), (pets["taxes"], 0.0)]
    assert _ranked(limit=1) == [(pets["cats"], 1.0)]
    with db.session() as session:
        [hit] = semantic_search(session, "felines", limit=1)
    assert (hit.title, hit.snippet, hit.tags) == ("Cats", "They purr.", [])


@pytest.mark.usefixtures("database")
def test_semantic_search_by_tag(pets: dict[str, int]) -> None:
    assert _ranked(tags=["#admin"]) == [(pets["taxes"], 0.0)]
    assert _ranked(tags=["pets", "admin"]) == []


@pytest.mark.usefixtures("database")
def test_semantic_search_skips_deleted_unembedded_and_other_models(pets: dict[str, int]) -> None:
    _add("Never embedded")
    with db.session() as session:
        delete_note(session, pets["dogs"])
        session.get_one(NoteEmbedding, pets["taxes"]).model = "old/model"
        session.commit()
    assert _ranked() == [(pets["cats"], 1.0)]


@pytest.mark.usefixtures("database")
def test_semantic_search_errors(embedder: FakeEmbedder) -> None:
    with db.session() as session:
        with pytest.raises(EmptyQuery):
            semantic_search(session, "  ")
        assert embedder.calls == []
        embedder.fail_after = 0
        with pytest.raises(EmbeddingError):
            semantic_search(session, "anything")


@pytest.fixture
def client(database: None, api_tokens: dict[str, str]) -> TestClient:
    return TestClient(app, headers={"Authorization": f"Bearer {api_tokens['ro']}"})


def test_api_semantic_search(client: TestClient, pets: dict[str, int]) -> None:
    hits = client.get("/api/search?q=felines&mode=semantic").json()["hits"]
    assert [(hit["id"], round(hit["score"], 4)) for hit in hits] == [
        (pets["cats"], 1.0),
        (pets["dogs"], 0.8),
        (pets["taxes"], 0.0),
    ]
    assert hits[0]["snippet"] == "They purr."
    limited = client.get("/api/search?q=felines&mode=semantic&limit=1&tag=pets").json()
    assert [hit["id"] for hit in limited["hits"]] == [pets["dogs"]]


def test_api_semantic_search_errors(client: TestClient, embedder: FakeEmbedder) -> None:
    assert client.get("/api/search?q=%20&mode=semantic").status_code == 422
    embedder.fail_after = 0
    response = client.get("/api/search?q=x&mode=semantic")
    assert (response.status_code, response.json()) == (
        502,
        {"detail": "OpenRouter returned 500."},
    )


# Ranking in the web UI.


def test_web_ranking(client: TestClient, pets: dict[str, int]) -> None:
    html = client.get("/search?q=felines").text
    assert "Ranked by similarity · 3" in html
    assert html.index("Cats") < html.index("Dogs") < html.index("Taxes")
    assert f'hx-get="/notes/{pets["cats"]}"' in html
    assert f'hx-push-url="/n/{pets["cats"]}"' in html
    assert ">1.00<" in html and ">0.80<" in html
    assert "They purr." in html

    html = client.get("/search?q=felines&tag=pets").text
    assert "Ranked by similarity · 1" in html
    assert "Dogs" in html and "Cats" not in html
    assert "No notes to rank." in client.get("/search?q=felines&tag=pets&tag=admin").text


def test_web_ranking_errors(client: TestClient, embedder: FakeEmbedder) -> None:
    response = client.get("/search?q=%20")
    assert response.status_code == 200
    assert "Search query cannot be empty." in response.text
    embedder.fail_after = 0
    response = client.get("/search?q=felines")
    assert response.status_code == 200
    assert RANKING_UNAVAILABLE.replace("'", "&#39;") in response.text
    assert "data-close-ranking" in response.text


def test_web_ranking_requires_login(api_tokens: dict[str, str]) -> None:
    response = TestClient(app, follow_redirects=False).get("/search?q=x")
    assert response.status_code == 303
