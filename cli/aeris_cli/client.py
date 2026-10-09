"""A thin client for the aeris JSON API. Responses are returned as parsed JSON, unchanged."""

from collections.abc import Sequence
from datetime import datetime
from typing import Any

import httpx

from aeris_cli.config import Config

TIMEOUT_SECONDS = 30  # Generous: the first request after a while wakes the server and database.


class AerisError(Exception):
    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status  # The HTTP status, if the server answered.


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

    def create_note(self, content: str) -> dict[str, Any]:
        return self._request("POST", "/api/notes", json={"content": content})

    def append_note(self, note_id: int, text: str) -> dict[str, Any]:
        """Add text to the end of a note as a new paragraph. Never conflicts."""
        return self._request("POST", f"/api/notes/{note_id}/append", json={"text": text})

    def delete_note(self, note_id: int) -> None:
        self._request("DELETE", f"/api/notes/{note_id}")

    def _get(self, path: str, params: dict[str, str | int]) -> dict[str, Any]:
        return self._request("GET", path, params=params)

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str | int] | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any:
        try:
            response = self._http.request(
                method, path, params=params, json=json, headers=self._headers
            )
        except httpx.HTTPError as error:
            raise AerisError(f"Could not reach {self._url}: {error}") from error
        if response.is_error:
            raise AerisError(_error_message(response), status=response.status_code)
        return response.json() if response.content else None


def _error_message(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        body = None
    detail = body.get("detail") if isinstance(body, dict) else None
    if isinstance(detail, str):
        return f"{detail} (HTTP {response.status_code})"
    return f"The server returned HTTP {response.status_code}."
