"""Embeddings from OpenRouter, for semantic search. Configured by `AERIS_OPENROUTER_API_KEY` and,
optionally, `AERIS_EMBEDDING_MODEL`."""

import os
from contextlib import nullcontext
from typing import Any

import httpx

API_KEY_VAR = "AERIS_OPENROUTER_API_KEY"
MODEL_VAR = "AERIS_EMBEDDING_MODEL"
DEFAULT_MODEL = "openai/text-embedding-3-small"
URL = "https://openrouter.ai/api/v1/embeddings"
TIMEOUT = 5.0


class EmbeddingError(Exception):
    """Embedding failed: no key, an HTTP or network error, or an unexpected response."""


def embedding_model() -> str:
    return os.environ.get(MODEL_VAR) or DEFAULT_MODEL


def embed(texts: list[str], *, client: httpx.Client | None = None) -> list[list[float]]:
    """One vector per text, in the same order. `client` lets tests swap the HTTP layer."""
    if not texts:
        return []
    key = os.environ.get(API_KEY_VAR)
    if not key:
        raise EmbeddingError(f"{API_KEY_VAR} is not set.")
    try:
        # Close the client only if we made it; a caller's client stays open for reuse.
        with nullcontext(client) if client else httpx.Client() as http:
            response = http.post(
                URL,
                headers={"Authorization": f"Bearer {key}"},
                json={"model": embedding_model(), "input": texts},
                timeout=TIMEOUT,
            )
            response.raise_for_status()
            body = response.json()
    except httpx.HTTPStatusError as error:
        raise EmbeddingError(f"OpenRouter returned {error.response.status_code}.") from error
    except (httpx.HTTPError, ValueError) as error:
        raise EmbeddingError(f"OpenRouter request failed: {error}") from error
    return _vectors(body, len(texts))


def _vectors(body: Any, count: int) -> list[list[float]]:
    try:
        items = sorted(body["data"], key=lambda item: item["index"])
        vectors = [[float(x) for x in item["embedding"]] for item in items]
    except (KeyError, TypeError, ValueError) as error:
        raise EmbeddingError("Unexpected response from OpenRouter.") from error
    if [item["index"] for item in items] != list(range(count)):
        raise EmbeddingError(f"Expected {count} embeddings, got {len(vectors)}.")
    return vectors
