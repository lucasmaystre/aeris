from collections.abc import Iterator
from typing import Annotated

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from aeris_server import auth
from aeris_server.auth import COOKIE_NAME, TOKENS_VAR, Token, authenticate, parse_tokens

RW = "rw-secret-" + "x" * 30
RO = "ro-secret-" + "y" * 30


@pytest.fixture(autouse=True)
def configured_tokens(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv(TOKENS_VAR, f"me:rw:{RW}, reader:ro:{RO}")
    auth.tokens.cache_clear()
    yield
    auth.tokens.cache_clear()


app = FastAPI()


@app.get("/read")
def read(token: Annotated[Token, Depends(auth.require_read)]) -> str:
    return token.name


@app.post("/write")
def write(token: Annotated[Token, Depends(auth.require_write)]) -> str:
    return token.name


client = TestClient(app)


# Parsing.


def test_parse_tokens() -> None:
    tokens = parse_tokens(f" me:rw:{RW} ,, reader : ro : {RO} ,")
    assert [(t.name, t.scope, t.secret) for t in tokens] == [("me", "rw", RW), ("reader", "ro", RO)]
    assert parse_tokens("") == []


def test_secret_not_in_repr() -> None:
    assert RW not in repr(parse_tokens(f"me:rw:{RW}"))


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ("me:rw", "expected name:scope:secret"),
        (f":rw:{RW}", "expected name:scope:secret"),
        (f"me:admin:{RW}", "scope must be ro or rw"),
        ("me:rw:short", "at least 32 characters"),
        (f"me:rw:{RW},me:ro:{RO}", "duplicate token name"),
    ],
)
def test_parse_tokens_errors(value: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        parse_tokens(value)


def test_authenticate() -> None:
    assert (token := authenticate(RW)) is not None and token.name == "me"
    assert (token := authenticate(RO)) is not None and token.name == "reader"
    assert authenticate(RW + "x") is None


# Dependencies.


def test_no_credentials() -> None:
    response = client.get("/read")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_bearer_header() -> None:
    response = client.get("/read", headers={"Authorization": f"Bearer {RO}"})
    assert (response.status_code, response.json()) == (200, "reader")


def test_cookie() -> None:
    response = TestClient(app, cookies={COOKIE_NAME: RW}).get("/read")
    assert (response.status_code, response.json()) == (200, "me")


@pytest.mark.parametrize("header", ["Bearer wrong-secret", f"Basic {RW}", "Bearer", f"{RW}"])
def test_bad_credentials(header: str) -> None:
    assert client.get("/read", headers={"Authorization": header}).status_code == 401


def test_write_scopes() -> None:
    assert client.post("/write", headers={"Authorization": f"Bearer {RO}"}).status_code == 403
    response = client.post("/write", headers={"Authorization": f"Bearer {RW}"})
    assert (response.status_code, response.json()) == (200, "me")


def test_no_tokens_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(TOKENS_VAR)
    auth.tokens.cache_clear()
    assert client.get("/read", headers={"Authorization": f"Bearer {RW}"}).status_code == 401
