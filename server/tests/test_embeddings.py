import json
from collections.abc import Callable

import httpx
import pytest

from aeris_server import embeddings
from aeris_server.embeddings import API_KEY_VAR, MODEL_VAR, EmbeddingError, embed

KEY = "test-openrouter-key"


@pytest.fixture(autouse=True)
def api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(API_KEY_VAR, KEY)
    monkeypatch.delenv(MODEL_VAR, raising=False)


def fake(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def reply(*vectors: list[float], order: list[int] | None = None) -> httpx.Response:
    indices = order or list(range(len(vectors)))
    data = [{"object": "embedding", "index": i, "embedding": vectors[i]} for i in indices]
    return httpx.Response(200, json={"object": "list", "data": data, "model": "m"})


def test_sends_texts_with_key_and_model() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return reply([1.0, 2.0], [3.0, 4.0])

    assert embed(["a", "b"], client=fake(handler)) == [[1.0, 2.0], [3.0, 4.0]]
    (request,) = seen
    assert str(request.url) == embeddings.URL
    assert request.headers["Authorization"] == f"Bearer {KEY}"
    assert json.loads(request.content) == {
        "model": "openai/text-embedding-3-small",
        "input": ["a", "b"],
    }


def test_model_comes_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(MODEL_VAR, "other/model")
    models: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        models.append(json.loads(request.content)["model"])
        return reply([1.0])

    embed(["a"], client=fake(handler))
    assert models == ["other/model"]


def test_vectors_follow_input_order() -> None:
    client = fake(lambda request: reply([0.0], [1.0], [2.0], order=[2, 0, 1]))
    assert embed(["a", "b", "c"], client=client) == [[0.0], [1.0], [2.0]]


def test_no_texts_makes_no_request() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("unexpected request")

    assert embed([], client=fake(handler)) == []


def test_caller_client_stays_open() -> None:
    client = fake(lambda request: reply([1.0]))
    embed(["a"], client=client)
    assert not client.is_closed


def test_missing_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(API_KEY_VAR)
    with pytest.raises(EmbeddingError, match=API_KEY_VAR):
        embed(["a"], client=fake(lambda request: reply([1.0])))


@pytest.mark.parametrize("status", [401, 429, 500])
def test_http_errors(status: int) -> None:
    client = fake(lambda request: httpx.Response(status, json={"error": "nope"}))
    with pytest.raises(EmbeddingError, match=str(status)):
        embed(["a"], client=client)


def test_network_errors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    with pytest.raises(EmbeddingError, match="timed out"):
        embed(["a"], client=fake(handler))


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, text="not json"),
        httpx.Response(200, json={"error": {"message": "no data"}}),
        httpx.Response(200, json={"data": [{"index": 0, "embedding": ["x"]}]}),
    ],
)
def test_malformed_responses(response: httpx.Response) -> None:
    with pytest.raises(EmbeddingError):
        embed(["a"], client=fake(lambda request: response))


def test_wrong_number_of_vectors() -> None:
    with pytest.raises(EmbeddingError, match="Expected 2 embeddings, got 1"):
        embed(["a", "b"], client=fake(lambda request: reply([1.0])))
