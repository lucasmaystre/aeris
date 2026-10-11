"""The sandbox's own pieces, offline: no database, no server."""

import math

import pytest
import sandbox
from fastapi.testclient import TestClient

from aeris_server import embeddings
from aeris_server.app import app as production
from aeris_server.auth import COOKIE_NAME
from aeris_server.parsing import title


@pytest.fixture
def app(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    # Restore `embeddings.embed` afterwards: `create_app` swaps in the fake embedder.
    monkeypatch.setattr(embeddings, "embed", embeddings.embed)
    monkeypatch.delenv(embeddings.API_KEY_VAR, raising=False)
    return TestClient(sandbox.create_app(), follow_redirects=False)


def test_dev_login_sets_the_cookie(app: TestClient) -> None:
    response = app.get("/dev/login")
    assert (response.status_code, response.headers["location"]) == (303, "/")
    assert response.cookies[COOKIE_NAME] == sandbox.TOKEN
    assert embeddings.embed is sandbox.fake_embed


def test_other_paths_reach_the_production_app(app: TestClient) -> None:
    assert app.get("/healthz").json() == {"ok": True}
    assert app.get("/").status_code == 303  # Not logged in: off to /login.


def test_production_has_no_dev_routes() -> None:
    assert not any(getattr(route, "path", "").startswith("/dev") for route in production.routes)


def test_fake_embed_ranks_shared_words_closer() -> None:
    ray, kubernetes, soup = sandbox.fake_embed(
        ["ray cluster on kubernetes", "kubernetes cluster nodes", "tomato soup recipe"]
    )
    assert len(ray) == sandbox.DIMENSIONS
    assert math.isclose(sum(x * x for x in ray), 1.0)

    def cosine(a: list[float], b: list[float]) -> float:
        return sum(x * y for x, y in zip(a, b, strict=True))

    assert cosine(ray, kubernetes) > cosine(ray, soup)


def test_fixtures_are_notes() -> None:
    paths = sorted(sandbox.FIXTURES.glob("*.md"))
    assert len(paths) >= len(sandbox.AGES)
    for path in paths:
        assert title(path.read_text()), path.name


def test_styleguide_renders_every_section(app: TestClient) -> None:
    page = app.get("/dev/styleguide")
    assert page.status_code == 200
    for heading in ["Colors", "Type", "Controls", "aeris components"]:
        assert f">{heading}</h2>" in page.text
    # The real partials, with fixture data.
    assert 'id="note-list"' in page.text
    assert "Ranked by similarity · 6" in page.text
    assert "Running a Ray cluster on Kubernetes</h1>" in page.text
    assert 'Edit note <span class="font-mono">#1</span>' in page.text
    assert "changed since you opened it" in page.text
    assert 'action="/login"' in page.text
    assert 'data-color="primary"' in page.text
    assert "Note not found." in page.text and "Note #1 deleted." in page.text


def test_sample_notes_match_the_fixtures() -> None:
    notes = sandbox.sample_notes()
    assert [note.id for note in notes] == list(range(1, len(notes) + 1))
    assert notes[1].tags == ["infra/kubernetes", "infra/ray"]
    assert notes[0].updated_at >= notes[1].updated_at
