import json

import pytest
from fastapi.testclient import TestClient

from aeris_server import db, notes
from aeris_server.app import app


@pytest.fixture
def client(database: None, api_tokens: dict[str, str]) -> TestClient:
    # A read-only token: every read endpoint must accept it.
    return TestClient(app, headers={"Authorization": f"Bearer {api_tokens['ro']}"})


def _create(content: str) -> int:
    with db.session() as session:
        return notes.create_note(session, content).id


@pytest.mark.parametrize(
    "path",
    [
        "/api/notes",
        "/api/notes?ids=1",
        "/api/notes/1",
        "/api/search?q=x",
        "/api/tags",
        "/api/export",
    ],
)
@pytest.mark.usefixtures("api_tokens")
def test_requires_auth(path: str) -> None:
    assert TestClient(app).get(path).status_code == 401


def test_list_notes(client: TestClient) -> None:
    first = _create("# First\n\nTags: #work")
    second = _create("Second")

    def ids(params: str = "") -> list[int]:
        body = client.get(f"/api/notes{params}").json()
        assert body["missing"] == []
        return [note["id"] for note in body["notes"]]

    assert ids() == [second, first]
    assert ids("?tag=work") == [first]
    assert ids("?limit=1") == [second]
    assert ids("?order=updated&since=2000-01-01") == [second, first]
    assert ids("?since=2100-01-01T00:00:00Z") == []
    [note, _] = client.get("/api/notes?content=false").json()["notes"]
    assert note["content"] is None and note["title"] == "Second"


def test_list_notes_validation(client: TestClient) -> None:
    for params in ["?limit=0", "?order=random", "?since=yesterday", "?ids=1,x", "?ids="]:
        assert client.get(f"/api/notes{params}").status_code == 422, params


def test_batch_fetch(client: TestClient) -> None:
    a, b = _create("A"), _create("B")
    body = client.get(f"/api/notes?ids={b},999,{a},{b}&tag=ignored").json()
    assert [note["id"] for note in body["notes"]] == [b, a]
    assert body["missing"] == [999]


def test_get_note(client: TestClient) -> None:
    note_id = _create("# Title\n\nTags: #x")
    note = client.get(f"/api/notes/{note_id}").json()
    assert note["id"] == note_id
    assert (note["title"], note["tags"], note["deleted"]) == ("Title", ["x"], False)
    assert set(note) == {"id", "title", "tags", "created_at", "updated_at", "content", "deleted"}
    response = client.get("/api/notes/999")
    assert (response.status_code, response.json()) == (404, {"detail": "No note with id 999."})


def test_search(client: TestClient) -> None:
    note_id = _create("Un été chaud")
    [hit] = client.get("/api/search?q=ETE").json()["hits"]
    assert (hit["id"], hit["snippet"], hit["score"]) == (note_id, "Un été chaud", None)
    assert "content" not in hit
    assert client.get("/api/search?q=%20").status_code == 422
    assert client.get("/api/search?q=x&mode=semantic").status_code == 422


def test_tags(client: TestClient) -> None:
    _create("Tags: #b, #a")
    _create("Tags: #a")
    assert client.get("/api/tags").json() == {
        "tags": [{"tag": "a", "count": 2}, {"tag": "b", "count": 1}]
    }


def test_export(client: TestClient) -> None:
    kept, gone = _create("Kept"), _create("Gone")
    with db.session() as session:
        notes.delete_note(session, gone)
    response = client.get("/api/export")
    assert response.headers["content-type"] == "application/x-ndjson"
    lines = [json.loads(line) for line in response.text.splitlines()]
    assert [(n["id"], n["deleted"]) for n in lines] == [(kept, False), (gone, True)]
