"""A thin client for the aeris JSON API. Responses are returned as parsed JSON, unchanged."""

from collections.abc import Sequence
from datetime import datetime
from typing import Any

import httpx

from aeris_cli.config import Config

TIMEOUT_SECONDS = 30  # Generous: the first request after a while wakes the server and database.


class AerisError(Exception):
    pass


class Client:
    def __init__(self, config: Config, http: httpx.Client | None = None) -> None:
        self._url = config.url
        self._http = http or httpx.Client(base_url=config.url, timeout=TIMEOUT_SECONDS)
        self._headers = {"Authorization": f"Bearer {config.token}"}

    def list_notes(
        self,
        *,
        limit: int | None = None,
        since: datetime | None = None,
        tag: str | None = None,
        order: str = "created",
    ) -> dict[str, Any]:
        """List notes newest first, without their content."""
        params: dict[str, str | int] = {"order": order, "content": "false"}
        if limit is not None:
            params["limit"] = limit
        if since is not None:
            params["since"] = since.isoformat()
        if tag is not None:
            params["tag"] = tag
        return self._get("/api/notes", params)

    def get_notes(self, ids: Sequence[int]) -> dict[str, Any]:
        """Fetch several notes in one request; `missing` lists IDs that weren't found."""
        return self._get("/api/notes", {"ids": ",".join(str(note_id) for note_id in ids)})

    def search(
        self, query: str, *, tag: str | None = None, limit: int | None = None
    ) -> dict[str, Any]:
        """Notes containing `query`, ignoring case and accents, newest first, with snippets."""
        params: dict[str, str | int] = {"q": query}
        if tag is not None:
            params["tag"] = tag
        if limit is not None:
            params["limit"] = limit
        return self._get("/api/search", params)

    def list_tags(self) -> dict[str, Any]:
        """Every tag in use, alphabetically, with note counts."""
        return self._get("/api/tags", {})

    def _get(self, path: str, params: dict[str, str | int]) -> dict[str, Any]:
        try:
            response = self._http.get(path, params=params, headers=self._headers)
        except httpx.HTTPError as error:
            raise AerisError(f"Could not reach {self._url}: {error}") from error
        if response.is_error:
            raise AerisError(_error_message(response))
        return response.json()


def _error_message(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        body = None
    detail = body.get("detail") if isinstance(body, dict) else None
    if isinstance(detail, str):
        return f"{detail} (HTTP {response.status_code})"
    return f"The server returned HTTP {response.status_code}."
