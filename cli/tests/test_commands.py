import json
import sys
import time
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
import typer
from typer.testing import CliRunner

from aeris_cli import main
from aeris_cli.client import Client
from aeris_cli.config import Config
from aeris_cli.main import app, parse_since
from aeris_server.notes import NoteData, SearchHit, TagCount

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
    """Records requests and answers with queued responses, then with a default one."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.queue: list[tuple[int, Any]] = []
        self.status = 200
        self.body: Any = {"notes": [], "missing": []}

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        status, body = self.queue.pop(0) if self.queue else (self.status, self.body)
        if body is None:
            return httpx.Response(status)
        if isinstance(body, str):
            return httpx.Response(status, text=body)
        return httpx.Response(status, json=body)

    @property
    def sent(self) -> tuple[str, str, Any]:
        """Method, path and JSON body of the last request."""
        request = self.requests[-1]
        body = json.loads(request.content) if request.content else None
        return request.method, request.url.path, body

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


# search.


def _hit(note: dict[str, Any], snippet: str) -> dict[str, Any]:
    """A search hit as the server serializes it."""
    fields = {key: note[key] for key in ["id", "title", "tags", "created_at", "updated_at"]}
    return SearchHit.model_validate({**fields, "snippet": snippet, "score": None}).model_dump(
        mode="json"
    )


def test_search(server: FakeServer) -> None:
    server.body = {"hits": [_hit(NOTE_12, "…about twelve…"), _hit(NOTE_7, "Body of seven.")]}
    result = runner.invoke(app, ["search", "distributed", "systems"])
    assert result.exit_code == 0
    assert result.stdout.splitlines() == [
        "12  2026-10-05 13:30  Twelve",
        "                      …about twelve…",
        " 7  2026-10-01 10:00  Seven  #work",
        "                      Body of seven.",
    ]
    assert server.params == {"q": "distributed systems", "limit": "30"}
    assert server.requests[-1].url.path == "/api/search"


def test_search_options(server: FakeServer) -> None:
    server.body = {"hits": []}
    runner.invoke(app, ["search", "x", "--tag", "work", "--limit", "3"])
    assert server.params == {"q": "x", "tag": "work", "limit": "3"}


def test_search_no_matches(server: FakeServer) -> None:
    server.body = {"hits": []}
    result = runner.invoke(app, ["search", "nothing", "here"])
    assert (result.exit_code, result.stdout) == (0, "")
    assert result.stderr == "No notes match 'nothing here'.\n"


def test_search_json(server: FakeServer) -> None:
    server.body = {"hits": [_hit(NOTE_7, "Body of seven.")]}
    result = runner.invoke(app, ["search", "seven", "--json"])
    assert json.loads(result.stdout) == server.body


def test_search_empty_query(server: FakeServer) -> None:
    server.status, server.body = 422, {"detail": "Search query cannot be empty."}
    result = runner.invoke(app, ["search", " "])
    assert (result.exit_code, result.stderr) == (
        1,
        "Error: Search query cannot be empty. (HTTP 422)\n",
    )
    assert runner.invoke(app, ["search"]).exit_code == 2


# ask.


def test_ask(server: FakeServer) -> None:
    server.body = {
        "hits": [
            {**_hit(NOTE_7, "Body of seven."), "score": 0.6234},
            {**_hit(NOTE_12, ""), "score": 0.4},
        ]
    }
    result = runner.invoke(app, ["ask", "what", "about", "work?"])
    assert result.exit_code == 0
    assert result.stdout.splitlines() == [
        "0.62   7  2026-10-01 10:00  Seven  #work",
        "                            Body of seven.",
        "0.40  12  2026-10-05 13:30  Twelve",
    ]
    assert server.params == {"q": "what about work?", "mode": "semantic", "limit": "10"}
    assert server.requests[-1].url.path == "/api/search"


def test_ask_options_and_json(server: FakeServer) -> None:
    server.body = {"hits": [{**_hit(NOTE_7, "Body of seven."), "score": 0.5}]}
    result = runner.invoke(app, ["ask", "x", "--tag", "work", "--limit", "3", "--json"])
    assert json.loads(result.stdout) == server.body
    assert server.params == {"q": "x", "mode": "semantic", "tag": "work", "limit": "3"}


def test_ask_no_hits(server: FakeServer) -> None:
    server.body = {"hits": []}
    result = runner.invoke(app, ["ask", "anything"])
    assert (result.exit_code, result.stdout, result.stderr) == (0, "", "No notes found.\n")


def test_ask_embedding_failure(server: FakeServer) -> None:
    server.status, server.body = 502, {"detail": "OpenRouter returned 500."}
    result = runner.invoke(app, ["ask", "anything", "--json"])
    assert result.exit_code == 1
    assert json.loads(result.stdout) == {"error": "OpenRouter returned 500.", "status": 502}


# tags.


def _tags(*pairs: tuple[str, int]) -> dict[str, Any]:
    return {"tags": [TagCount(tag=tag, count=count).model_dump() for tag, count in pairs]}


def test_tags(server: FakeServer) -> None:
    server.body = _tags(("project/aeris", 1), ("work", 12))
    result = runner.invoke(app, ["tags"])
    assert result.exit_code == 0
    assert result.stdout.splitlines() == [" 1  #project/aeris", "12  #work"]
    assert server.requests[-1].url.path == "/api/tags"


def test_tags_empty_and_json(server: FakeServer) -> None:
    server.body = _tags()
    assert runner.invoke(app, ["tags"]).stdout == ""
    server.body = _tags(("work", 2))
    assert json.loads(runner.invoke(app, ["tags", "--json"]).stdout) == server.body


# Writing: add, delete.


@pytest.fixture
def editor(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Pretend to be in a terminal, with an "editor" that writes the contents of a file."""
    text_file = tmp_path / "typed.txt"
    script = tmp_path / "editor.py"
    # `{current}` in the typed text stands for what the file held when the editor opened.
    script.write_text(
        "import pathlib, sys\n"
        "path = pathlib.Path(sys.argv[-1])\n"
        f"typed = pathlib.Path({str(text_file)!r}).read_text()\n"
        "path.write_text(typed.replace('{current}', path.read_text()))\n"
    )
    monkeypatch.setattr(main, "_interactive", lambda: True)
    monkeypatch.delenv("VISUAL", raising=False)
    monkeypatch.setenv("EDITOR", f"{sys.executable} {script} --some-flag")
    return text_file


def test_add_message(server: FakeServer) -> None:
    server.body = NOTE_12
    result = runner.invoke(app, ["add", "-m", "Twelve"])
    assert (result.exit_code, result.stdout) == (0, "Created note 12.\n")
    assert server.sent == ("POST", "/api/notes", {"content": "Twelve"})


def test_add_stdin(server: FakeServer) -> None:
    server.body = NOTE_12
    result = runner.invoke(app, ["add"], input="Piped\ntext\n")
    assert result.exit_code == 0
    assert server.sent[2] == {"content": "Piped\ntext\n"}


def test_add_editor(server: FakeServer, editor: Path) -> None:
    editor.write_text("# From the editor\n")
    server.body = NOTE_12
    result = runner.invoke(app, ["add"])
    assert result.exit_code == 0
    assert server.sent[2] == {"content": "# From the editor\n"}


def test_add_editor_emptied(server: FakeServer, editor: Path) -> None:
    editor.write_text("  \n")
    result = runner.invoke(app, ["add"])
    assert (result.exit_code, result.stdout) == (0, "Empty note, nothing saved.\n")
    assert server.requests == []


def test_add_editor_fails(server: FakeServer, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main, "_interactive", lambda: True)
    monkeypatch.setenv("VISUAL", "false")
    result = runner.invoke(app, ["add"])
    assert result.exit_code == 1
    assert result.stderr.startswith("Error: the editor failed")
    assert server.requests == []


@pytest.mark.parametrize(("args", "stdin"), [(["-m", " "], None), ([], ""), ([], "\n\n")])
def test_add_no_text(server: FakeServer, args: list[str], stdin: str | None) -> None:
    result = runner.invoke(app, ["add", *args], input=stdin)
    assert result.exit_code == 1
    assert result.stderr == f"Error: {main.NO_TEXT}\n"
    assert server.requests == []


def test_add_json(server: FakeServer) -> None:
    server.body = NOTE_12
    result = runner.invoke(app, ["add", "-m", "Twelve", "--json"])
    assert json.loads(result.stdout) == NOTE_12


def test_delete(server: FakeServer) -> None:
    server.status, server.body = 204, None
    result = runner.invoke(app, ["delete", "7"])
    assert (result.exit_code, result.stdout) == (0, "Deleted note 7.\n")
    assert server.sent == ("DELETE", "/api/notes/7", None)


def test_delete_missing_note(server: FakeServer) -> None:
    server.status, server.body = 404, {"detail": "No note with id 99."}
    result = runner.invoke(app, ["delete", "99"])
    assert (result.exit_code, result.stderr) == (1, "Error: No note with id 99. (HTTP 404)\n")


# edit.


EDITED_7 = {
    **NOTE_7,
    "content": "# Seven\n\nBody of seven, edited.",
    "updated_at": "2026-10-10T08:00:00Z",
}


def test_edit_in_editor(server: FakeServer, editor: Path) -> None:
    editor.write_text("{current}, edited.")
    server.queue = [(200, NOTE_7), (200, EDITED_7)]
    result = runner.invoke(app, ["edit", "7"])
    assert (result.exit_code, result.stdout) == (0, "Updated note 7.\n")
    assert [(r.method, r.url.path) for r in server.requests] == [
        ("GET", "/api/notes/7"),
        ("PUT", "/api/notes/7"),
    ]
    assert server.sent[2] == {
        "content": "# Seven\n\nBody of seven., edited.",
        "expected_updated_at": NOTE_7["updated_at"],
    }


@pytest.mark.parametrize(
    ("typed", "message"),
    [("{current}\n\n", "No changes.\n"), ("  \n", "Empty note, nothing saved.\n")],
)
def test_edit_nothing_to_save(server: FakeServer, editor: Path, typed: str, message: str) -> None:
    editor.write_text(typed)
    server.body = NOTE_7
    result = runner.invoke(app, ["edit", "7"])
    assert (result.exit_code, result.stdout) == (0, message)
    assert [r.method for r in server.requests] == ["GET"]


def test_edit_conflict_keeps_draft(server: FakeServer, editor: Path) -> None:
    editor.write_text("My careful rewrite.")
    server.queue = [
        (200, NOTE_7),
        (409, {"detail": "Note 7 was changed at …", "current": EDITED_7}),
    ]
    result = runner.invoke(app, ["edit", "7"])
    assert result.exit_code == 1
    prefix = "Error: Note 7 changed while you were editing; nothing saved. Your text is in "
    assert result.stderr.startswith(prefix)
    draft = Path(result.stderr.removeprefix(prefix).strip())
    assert draft.read_text() == "My careful rewrite."
    draft.unlink()


def test_edit_missing_note(server: FakeServer, editor: Path) -> None:
    server.status, server.body = 404, {"detail": "No note with id 99."}
    result = runner.invoke(app, ["edit", "99"])
    assert (result.exit_code, result.stderr) == (1, "Error: No note with id 99. (HTTP 404)\n")


def test_edit_needs_terminal_or_stdin(server: FakeServer) -> None:
    result = runner.invoke(app, ["edit", "7"])
    assert result.exit_code == 1
    assert result.stderr == "Error: Not in a terminal: use --stdin to pass the new content.\n"
    assert server.requests == []


def test_edit_stdin(server: FakeServer) -> None:
    server.body = EDITED_7
    result = runner.invoke(app, ["edit", "7", "--stdin"], input="New content\n")
    assert (result.exit_code, result.stdout) == (0, "Updated note 7.\n")
    assert server.sent == ("PUT", "/api/notes/7", {"content": "New content\n"})


def test_edit_stdin_expected_updated_at(server: FakeServer) -> None:
    server.body = EDITED_7
    args = ["edit", "7", "--stdin", "--expected-updated-at", NOTE_7["updated_at"], "--json"]
    result = runner.invoke(app, args, input="New")
    assert json.loads(result.stdout) == EDITED_7
    assert server.sent[2] == {"content": "New", "expected_updated_at": NOTE_7["updated_at"]}


def test_edit_stdin_conflict(server: FakeServer) -> None:
    server.status, server.body = 409, {"detail": "Note 7 was changed at x.", "current": EDITED_7}
    result = runner.invoke(app, ["edit", "7", "--stdin", "--expected-updated-at", "x"], input="New")
    assert (result.exit_code, result.stderr) == (1, "Error: Note 7 was changed at x. (HTTP 409)\n")


def test_edit_stdin_empty(server: FakeServer) -> None:
    result = runner.invoke(app, ["edit", "7", "--stdin"], input=" ")
    assert (result.exit_code, result.stderr) == (
        1,
        "Error: No text to save: pipe the new content in.\n",
    )
    assert server.requests == []


def test_edit_expected_updated_at_needs_stdin(server: FakeServer) -> None:
    result = runner.invoke(app, ["edit", "7", "--expected-updated-at", "x"])
    assert result.exit_code == 2
    assert server.requests == []


# export.


DELETED_12 = {**NOTE_12, "deleted": True}
EXPORT = json.dumps(NOTE_7) + "\n" + json.dumps(DELETED_12) + "\n"


def test_export_default_path(
    server: FakeServer, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    server.body = EXPORT
    result = runner.invoke(app, ["export"])
    assert result.exit_code == 0
    [written] = list(tmp_path.glob("aeris-export-*.jsonl"))
    assert written.read_text() == EXPORT
    assert result.stdout == f"Exported 2 notes (1 deleted) to {written.name}.\n"
    assert server.requests[-1].url.path == "/api/export"


def test_export_to_stdout(server: FakeServer) -> None:
    server.body = json.dumps(NOTE_7) + "\n"
    result = runner.invoke(app, ["export", "-"])
    assert (result.exit_code, result.stdout) == (0, server.body)
    assert result.stderr == "Exported 1 note.\n"


def test_export_refuses_to_overwrite(server: FakeServer, tmp_path: Path) -> None:
    target = tmp_path / "backup.jsonl"
    target.write_text("precious")
    server.body = EXPORT
    result = runner.invoke(app, ["export", str(target)])
    assert result.exit_code == 1
    assert result.stderr == f"Error: {target} already exists; use --force to overwrite it.\n"
    assert (target.read_text(), server.requests) == ("precious", [])
    assert runner.invoke(app, ["export", str(target), "--force"]).exit_code == 0
    assert target.read_text() == EXPORT


def test_export_error_writes_nothing(server: FakeServer, tmp_path: Path) -> None:
    server.status, server.body = 401, {"detail": "Not authenticated."}
    target = tmp_path / "backup.jsonl"
    result = runner.invoke(app, ["export", str(target)])
    assert (result.exit_code, result.stderr) == (1, "Error: Not authenticated. (HTTP 401)\n")
    assert not target.exists()


# Errors with --json.


def test_json_error_from_server(server: FakeServer) -> None:
    server.status, server.body = 404, {"detail": "No note with id 99."}
    for args in (["delete", "99"], ["edit", "99", "--stdin"]):
        result = runner.invoke(app, [*args, "--json"], input="new")
        assert result.exit_code == 1, args
        assert json.loads(result.stdout) == {"error": "No note with id 99.", "status": 404}
        assert result.stderr == ""


def test_json_conflict_includes_current(server: FakeServer) -> None:
    server.status, server.body = 409, {"detail": "Note 7 was changed at x.", "current": EDITED_7}
    args = ["edit", "7", "--stdin", "--expected-updated-at", "x", "--json"]
    result = runner.invoke(app, args, input="New")
    assert result.exit_code == 1
    assert json.loads(result.stdout) == {
        "error": "Note 7 was changed at x.",
        "status": 409,
        "current": EDITED_7,
    }


def test_json_editor_conflict(server: FakeServer, editor: Path) -> None:
    editor.write_text("My rewrite.")
    server.queue = [
        (200, NOTE_7),
        (409, {"detail": "Note 7 was changed at x.", "current": EDITED_7}),
    ]
    result = runner.invoke(app, ["edit", "7", "--json"])
    body = json.loads(result.stdout)
    assert (body["status"], body["current"]) == (409, EDITED_7)
    draft = Path(body["error"].split("Your text is in ")[1])
    assert draft.read_text() == "My rewrite."
    draft.unlink()


def test_json_errors_without_server(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AERIS_CONFIG_PATH", str(tmp_path / "absent.yaml"))
    monkeypatch.delenv("AERIS_URL", raising=False)
    monkeypatch.delenv("AERIS_TOKEN", raising=False)
    result = runner.invoke(app, ["list", "--json"])
    assert result.exit_code == 1
    assert json.loads(result.stdout)["error"].startswith("Set AERIS_URL and AERIS_TOKEN")
    result = runner.invoke(app, ["add", "--json"], input="")
    assert json.loads(result.stdout) == {"error": main.NO_TEXT}


def test_delete_json(server: FakeServer) -> None:
    server.status, server.body = 204, None
    result = runner.invoke(app, ["delete", "7", "--json"])
    assert (result.exit_code, json.loads(result.stdout)) == (0, {"id": 7, "deleted": True})


def test_help_documents_exit_codes() -> None:
    assert "Exit codes: 0 success, 1 error, 2 usage error." in runner.invoke(app, ["--help"]).stdout


# Errors.


def test_server_error(server: FakeServer) -> None:
    server.status, server.body = 401, {"detail": "Not authenticated."}
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 1
    assert result.stderr == "Error: Not authenticated. (HTTP 401)\n"


def test_server_error_without_detail(server: FakeServer) -> None:
    server.status, server.body = 502, ["unexpected"]
    result = runner.invoke(app, ["show", "1"])
    assert (result.exit_code, result.stderr) == (
        1,
        "Error: Unexpected response from the server. (HTTP 502)\n",
    )


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
