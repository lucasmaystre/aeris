"""A thin client for the aeris JSON API. Responses are returned as parsed JSON, unchanged."""

from collections.abc import Sequence
from datetime import datetime
from typing import Any, Literal

import httpx

from aeris_cli.config import Config

TIMEOUT_SECONDS = 30  # Generous: the first request after a while wakes the server and database.


class AerisError(Exception):
    def __init__(
        self, message: str, status: int | None = None, current: dict[str, Any] | None = None
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status = status  # The HTTP status, if the server answered.
        self.current = current  # On a conflict (409): the note's latest version.


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
        self,
        query: str,
        *,
        mode: Literal["text", "semantic"] = "text",
        tag: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """Notes containing `query`, ignoring case and accents, newest first, with snippets.

        With `mode="semantic"`: the notes closest in meaning, best first, with scores.
        """
        params: dict[str, str | int] = {"q": query}
        if mode != "text":
            params["mode"] = mode
        if tag is not None:
            params["tag"] = tag
        if limit is not None:
            params["limit"] = limit
        return self._get("/api/search", params)

    def list_tags(self) -> dict[str, Any]:
        """Every tag in use, alphabetically, with note counts."""
        return self._get("/api/tags", {})

    def get_note(self, note_id: int) -> dict[str, Any]:
        return self._request("GET", f"/api/notes/{note_id}")

    def update_note(
        self, note_id: int, content: str, expected_updated_at: str | None = None
    ) -> dict[str, Any]:
        """Replace a note's content. With `expected_updated_at`, fails (409) if it changed since."""
        body: dict[str, Any] = {"content": content}
        if expected_updated_at is not None:
            body["expected_updated_at"] = expected_updated_at
        return self._request("PUT", f"/api/notes/{note_id}", json=body)

    def create_note(self, content: str) -> dict[str, Any]:
        return self._request("POST", "/api/notes", json={"content": content})

    def delete_note(self, note_id: int) -> None:
        self._request("DELETE", f"/api/notes/{note_id}")

    def export(self) -> str:
        """Every note, including deleted ones, as JSON Lines."""
        return self._send("GET", "/api/export").text

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
        response = self._send(method, path, params=params, json=json)
        return response.json() if response.content else None

    def _send(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str | int] | None = None,
        json: dict[str, Any] | None = None,
    ) -> httpx.Response:
        try:
            response = self._http.request(
                method, path, params=params, json=json, headers=self._headers
            )
        except httpx.HTTPError as error:
            raise AerisError(f"Could not reach {self._url}: {error}") from error
        if response.is_error:
            raise _error(response)
        return response


def _error(response: httpx.Response) -> AerisError:
    try:
        body = response.json()
    except ValueError:
        body = None
    body = body if isinstance(body, dict) else {}
    detail = body.get("detail")
    message = detail if isinstance(detail, str) else "Unexpected response from the server."
    current = body.get("current")
    return AerisError(
        message, status=response.status_code, current=current if isinstance(current, dict) else None
    )
