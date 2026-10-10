"""Single-user auth: named tokens from `AERIS_TOKENS`, sent as a Bearer header or a cookie."""

import hmac
import os
from dataclasses import dataclass, field
from functools import cache
from typing import Annotated, Literal

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

TOKENS_VAR = "AERIS_TOKENS"
COOKIE_NAME = "aeris_token"
MIN_SECRET_LENGTH = 32

Scope = Literal["ro", "rw"]

# Reads `Authorization: Bearer ...` and declares the scheme in the API docs. Without the header it
# yields None rather than failing, so the cookie can be tried next.
bearer = HTTPBearer(auto_error=False, description="A token's secret (see `AERIS_TOKENS`).")
Bearer = Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]


@dataclass(frozen=True)
class Token:
    name: str
    scope: Scope
    secret: str = field(repr=False)


def parse_tokens(value: str) -> list[Token]:
    """Parse `name:scope:secret` entries separated by commas. Scope is `ro` or `rw`."""
    tokens: list[Token] = []
    for number, entry in enumerate(value.split(","), start=1):
        if not entry.strip():
            continue
        parts = [part.strip() for part in entry.split(":", 2)]
        if len(parts) != 3 or not parts[0]:
            raise ValueError(f"{TOKENS_VAR} entry {number}: expected name:scope:secret.")
        name, scope, secret = parts
        if scope != "ro" and scope != "rw":
            raise ValueError(f"{TOKENS_VAR} token {name!r}: scope must be ro or rw.")
        if len(secret) < MIN_SECRET_LENGTH:
            raise ValueError(
                f"{TOKENS_VAR} token {name!r}: secret must be at least {MIN_SECRET_LENGTH} characters."
            )
        if any(token.name == name for token in tokens):
            raise ValueError(f"{TOKENS_VAR}: duplicate token name {name!r}.")
        tokens.append(Token(name=name, scope=scope, secret=secret))
    return tokens


@cache
def tokens() -> tuple[Token, ...]:
    """The configured tokens. With `AERIS_TOKENS` unset there are none, so every request fails."""
    return tuple(parse_tokens(os.environ.get(TOKENS_VAR, "")))


def authenticate(secret: str) -> Token | None:
    """Find the token with this secret, comparing against all of them in constant time."""
    match = None
    for token in tokens():
        if hmac.compare_digest(secret.encode(), token.secret.encode()):
            match = token
    return match


def require_read(request: Request, credentials: Bearer) -> Token:
    """FastAPI dependency: any valid token, from the Bearer header or the cookie."""
    secret = (credentials and credentials.credentials) or request.cookies.get(COOKIE_NAME)
    token = authenticate(secret) if secret else None
    if token is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Not authenticated.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token


def require_write(token: Annotated[Token, Depends(require_read)]) -> Token:
    """FastAPI dependency: a valid token with write access."""
    if token.scope != "rw":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This token is read-only.")
    return token
