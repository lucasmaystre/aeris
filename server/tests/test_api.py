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
    assert client.get("/api/search?q=x&mode=fuzzy").status_code == 422


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


# Writes.


@pytest.fixture
def writer(database: None, api_tokens: dict[str, str]) -> TestClient:
    return TestClient(app, headers={"Authorization": f"Bearer {api_tokens['rw']}"})


WRITES = [
    ("POST", "/api/notes", {"content": "x"}),
    ("PUT", "/api/notes/1", {"content": "x"}),
    ("POST", "/api/notes/1/append", {"text": "x"}),
    ("DELETE", "/api/notes/1", None),
]


@pytest.mark.parametrize(("method", "path", "body"), WRITES)
def test_writes_require_rw(
    method: str, path: str, body: dict[str, str] | None, api_tokens: dict[str, str]
) -> None:
    assert TestClient(app).request(method, path, json=body).status_code == 401
    reader = TestClient(app, headers={"Authorization": f"Bearer {api_tokens['ro']}"})
    assert reader.request(method, path, json=body).status_code == 403


def test_create_note(writer: TestClient) -> None:
    response = writer.post("/api/notes", json={"content": "  # New\n\nTags: #x  "})
    assert response.status_code == 201
    note = response.json()
    assert response.headers["location"] == f"/api/notes/{note['id']}"
    assert (note["title"], note["tags"], note["content"]) == ("New", ["x"], "# New\n\nTags: #x")
    assert writer.get(response.headers["location"]).json() == note


def test_create_note_invalid(writer: TestClient) -> None:
    assert writer.post("/api/notes", json={"content": " "}).status_code == 422
    assert writer.post("/api/notes", json={}).status_code == 422


def test_update_note_round_trip(writer: TestClient) -> None:
    created = writer.post("/api/notes", json={"content": "v1"}).json()
    # The timestamp from a response must work as `expected_updated_at`, to the microsecond.
    body = {"content": "v2", "expected_updated_at": created["updated_at"]}
    response = writer.put(f"/api/notes/{created['id']}", json=body)
    assert response.status_code == 200
    assert response.json()["content"] == "v2"
    assert response.json()["updated_at"] != created["updated_at"]


def test_update_note_stale(writer: TestClient) -> None:
    created = writer.post("/api/notes", json={"content": "v1"}).json()
    path = f"/api/notes/{created['id']}"
    writer.put(path, json={"content": "v2"})
    response = writer.put(
        path, json={"content": "v3", "expected_updated_at": created["updated_at"]}
    )
    assert response.status_code == 409
    assert response.json()["current"]["content"] == "v2"
    assert response.json()["detail"].startswith(f"Note {created['id']} was changed at ")
    assert writer.get(path).json()["content"] == "v2"


def test_update_note_errors(writer: TestClient) -> None:
    assert writer.put("/api/notes/999", json={"content": "x"}).status_code == 404
    created = writer.post("/api/notes", json={"content": "v1"}).json()
    assert writer.put(f"/api/notes/{created['id']}", json={"content": ""}).status_code == 422


def test_append_note(writer: TestClient) -> None:
    created = writer.post("/api/notes", json={"content": "Start"}).json()
    path = f"/api/notes/{created['id']}/append"
    response = writer.post(path, json={"text": "More"})
    assert (response.status_code, response.json()["content"]) == (200, "Start\n\nMore")
    assert writer.post(path, json={"text": " "}).status_code == 422
    assert writer.post("/api/notes/999/append", json={"text": "x"}).status_code == 404


def test_delete_note(writer: TestClient) -> None:
    created = writer.post("/api/notes", json={"content": "Doomed"}).json()
    path = f"/api/notes/{created['id']}"
    response = writer.delete(path)
    assert (response.status_code, response.content) == (204, b"")
    assert writer.get(path).status_code == 404
    assert writer.delete(path).status_code == 404
