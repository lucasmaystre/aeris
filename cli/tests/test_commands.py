import json
import time
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
import typer
from typer.testing import CliRunner

from aeris_cli import main
from aeris_cli.client import Client
from aeris_cli.config import Config
from aeris_cli.main import app, parse_since
from aeris_server.notes import NoteData

runner = CliRunner()


def _note(
    note_id: int, content: str, tags: list[str], created: str, updated: str
) -> dict[str, Any]:
    """A note as the server serializes it, so field names can't drift from the API."""
    title = content.splitlines()[0].removeprefix("# ") if content else ""
    note = NoteData(
        id=note_id,
        title=title,
        tags=tags,
        created_at=datetime.fromisoformat(created),
        updated_at=datetime.fromisoformat(updated),
        content=content,
        deleted=False,
    )
    return note.model_dump(mode="json")


NOTE_7 = _note(
    7, "# Seven\n\nBody of seven.", ["work"], "2026-10-01T09:00:00Z", "2026-10-09T16:48:00Z"
)
NOTE_12 = _note(12, "Twelve", [], "2026-10-05T12:30:00Z", "2026-10-05T12:30:00Z")
UNTITLED = _note(3, "", ["a", "b"], "2026-09-01T00:00:00Z", "2026-09-01T00:00:00Z")


class FakeServer:
    """Records requests and answers with a canned response."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.status = 200
        self.body: Any = {"notes": [], "missing": []}

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(self.status, json=self.body)

    @property
    def params(self) -> dict[str, str]:
        return dict(self.requests[-1].url.params)


@pytest.fixture(autouse=True)
def london_time() -> Iterator[None]:
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("TZ", "Europe/London")
        time.tzset()
        yield
    time.tzset()


@pytest.fixture
def server(monkeypatch: pytest.MonkeyPatch) -> FakeServer:
    fake = FakeServer()
    http = httpx.Client(transport=httpx.MockTransport(fake.handle), base_url="https://aeris.test")
    client = Client(Config(url="https://aeris.test", token="t0ken"), http=http)
    monkeypatch.setattr(main, "make_client", lambda: client)
    return fake


# --last parsing.


NOW = datetime(2026, 10, 9, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("value", "delta"),
    [
        ("2 days", timedelta(days=2)),
        ("1 day", timedelta(days=1)),
        ("3h", timedelta(hours=3)),
        ("45 min", timedelta(minutes=45)),
        ("10 Minutes", timedelta(minutes=10)),
        ("1 week", timedelta(weeks=1)),
        (" 2w ", timedelta(weeks=2)),
    ],
)
def test_parse_since_duration(value: str, delta: timedelta) -> None:
    assert parse_since(value, now=NOW) == NOW - delta


def test_parse_since_dates() -> None:
    assert parse_since("2026-10-01T08:00:00+00:00") == datetime(2026, 10, 1, 8, tzinfo=UTC)
    # A bare date is local midnight: 23:00 UTC the day before, in London summer time.
    assert parse_since("2026-10-01") == datetime(2026, 9, 30, 23, tzinfo=UTC)


@pytest.mark.parametrize("value", ["yesterday", "2 fortnights", "", "-1 days"])
def test_parse_since_invalid(value: str) -> None:
    with pytest.raises(typer.BadParameter):
        parse_since(value)


# list.


def test_list(server: FakeServer) -> None:
    server.body = {"notes": [NOTE_12, NOTE_7, UNTITLED], "missing": []}
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0
    assert result.stdout.splitlines() == [
        "12  2026-10-05 13:30  Twelve",
        " 7  2026-10-01 10:00  Seven  #work",
        " 3  2026-09-01 01:00  (untitled)  #a  #b",
    ]
    assert server.params == {"order": "created", "content": "false", "limit": "30"}
    assert server.requests[-1].headers["authorization"] == "Bearer t0ken"


def test_list_options(server: FakeServer) -> None:
    server.body = {"notes": [NOTE_7], "missing": []}
    args = ["list", "--order", "updated", "--limit", "5", "--tag", "work", "--last", "2026-10-01"]
    result = runner.invoke(app, args)
    assert result.exit_code == 0
    # Sorted by update, so the update time is shown.
    assert result.stdout == "7  2026-10-09 17:48  Seven  #work\n"
    assert server.params == {
        "order": "updated",
        "content": "false",
        "limit": "5",
        "tag": "work",
        "since": "2026-10-01T00:00:00+01:00",
    }


def test_list_json(server: FakeServer) -> None:
    server.body = {"notes": [NOTE_7], "missing": []}
    result = runner.invoke(app, ["list", "--json"])
    assert result.exit_code == 0
    assert json.loads(result.stdout) == server.body


def test_list_rejects_bad_options(server: FakeServer) -> None:
    assert runner.invoke(app, ["list", "--last", "yesterday"]).exit_code == 2
    assert runner.invoke(app, ["list", "--limit", "0"]).exit_code == 2
    assert runner.invoke(app, ["list", "--order", "random"]).exit_code == 2
    assert server.requests == []


# show.


def test_show(server: FakeServer) -> None:
    server.body = {"notes": [NOTE_12, NOTE_7], "missing": []}
    result = runner.invoke(app, ["show", "12", "7"])
    assert result.exit_code == 0
    assert result.stdout == (
        "# 12 2026-10-05 13:30\n\nTwelve\n\n\n# 7 2026-10-01 10:00\n\n# Seven\n\nBody of seven.\n"
    )
    assert server.params == {"ids": "12,7"}


def test_show_missing(server: FakeServer) -> None:
    server.body = {"notes": [NOTE_7], "missing": [99]}
    result = runner.invoke(app, ["show", "7", "99"])
    assert result.exit_code == 1
    assert result.stdout.startswith("# 7 ")
    assert result.stderr == "No note with id 99.\n"


def test_show_json(server: FakeServer) -> None:
    server.body = {"notes": [NOTE_7], "missing": [99]}
    result = runner.invoke(app, ["show", "7", "99", "--json"])
    assert result.exit_code == 1
    assert json.loads(result.stdout) == server.body


def test_show_needs_ids(server: FakeServer) -> None:
    assert runner.invoke(app, ["show"]).exit_code == 2
    assert runner.invoke(app, ["show", "abc"]).exit_code == 2


# Errors.


def test_server_error(server: FakeServer) -> None:
    server.status, server.body = 401, {"detail": "Not authenticated."}
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 1
    assert result.stderr == "Error: Not authenticated. (HTTP 401)\n"


def test_server_error_without_detail(server: FakeServer) -> None:
    server.status, server.body = 502, ["unexpected"]
    result = runner.invoke(app, ["show", "1"])
    assert (result.exit_code, result.stderr) == (1, "Error: The server returned HTTP 502.\n")


def test_unreachable(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    http = httpx.Client(transport=httpx.MockTransport(refuse), base_url="https://aeris.test")
    client = Client(Config(url="https://aeris.test", token="t"), http=http)
    monkeypatch.setattr(main, "make_client", lambda: client)
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 1
    assert result.stderr.startswith("Error: Could not reach https://aeris.test: connection refused")


def test_missing_config(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AERIS_CONFIG_PATH", str(tmp_path / "absent.yaml"))
    monkeypatch.delenv("AERIS_URL", raising=False)
    monkeypatch.delenv("AERIS_TOKEN", raising=False)
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 1
    assert result.stderr.startswith("Error: Set AERIS_URL and AERIS_TOKEN")
