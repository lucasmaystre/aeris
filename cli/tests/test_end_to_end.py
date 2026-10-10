"""The CLI against the real app and database: command → HTTP → API → service → Postgres."""

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from aeris_cli import main
from aeris_cli.client import Client
from aeris_cli.config import Config
from aeris_cli.main import app as cli
from aeris_server.app import app as server

runner = CliRunner()

pytestmark = pytest.mark.usefixtures("database")


def _use_token(monkeypatch: pytest.MonkeyPatch, secret: str) -> None:
    """Route the CLI's requests to the in-process server app, authenticated with `secret`."""
    client = Client(Config(url="http://testserver", token=secret), http=TestClient(server))
    monkeypatch.setattr(main, "make_client", lambda: client)


def _run(*args: str, stdin: str | None = None) -> Any:
    """Run a CLI command with --json and return its parsed output."""
    result = runner.invoke(cli, [*args, "--json"], input=stdin)
    return json.loads(result.stdout) if result.stdout else None


def test_scenario(monkeypatch: pytest.MonkeyPatch, api_tokens: dict[str, str]) -> None:
    _use_token(monkeypatch, api_tokens["rw"])

    created = _run("add", "-m", "# Été plans\n\nGo to the sea.\n\nTags: #travel, #summer")
    note_id = created["id"]
    assert (created["title"], created["tags"]) == ("Été plans", ["summer", "travel"])

    listed = runner.invoke(cli, ["list"])
    assert listed.exit_code == 0
    assert "Été plans  #summer  #travel" in listed.stdout

    shown = runner.invoke(cli, ["show", str(note_id)])
    assert "Go to the sea." in shown.stdout

    [hit] = _run("search", "ete", "PLANS")["hits"]
    assert hit["id"] == note_id

    assert _run("tags")["tags"] == [{"tag": "summer", "count": 1}, {"tag": "travel", "count": 1}]

    # Edit with the timestamp read from `show`, as an agent would.
    [before] = _run("show", str(note_id))["notes"]
    edit = ["edit", str(note_id), "--stdin", "--expected-updated-at", before["updated_at"]]
    edited = _run(*edit, stdin="# Été plans\n\nMountains instead.")
    assert edited["content"] == "# Été plans\n\nMountains instead."
    assert edited["tags"] == []

    # The same edit again is now stale: refused, with the latest version attached.
    stale = runner.invoke(cli, [*edit, "--json"], input="Overwrite!")
    assert stale.exit_code == 1
    conflict = json.loads(stale.stdout)
    assert conflict["status"] == 409
    assert conflict["current"]["content"] == "# Été plans\n\nMountains instead."

    assert _run("delete", str(note_id)) == {"id": note_id, "deleted": True}
    missing = runner.invoke(cli, ["show", str(note_id)])
    assert (missing.exit_code, missing.stderr) == (1, f"No note with id {note_id}.\n")

    exported = runner.invoke(cli, ["export", "-"])
    [line] = exported.stdout.splitlines()
    assert (json.loads(line)["id"], json.loads(line)["deleted"]) == (note_id, True)


def test_read_only_token(monkeypatch: pytest.MonkeyPatch, api_tokens: dict[str, str]) -> None:
    _use_token(monkeypatch, api_tokens["ro"])
    assert runner.invoke(cli, ["list"]).exit_code == 0
    result = runner.invoke(cli, ["add", "-m", "Nope", "--json"])
    assert result.exit_code == 1
    assert json.loads(result.stdout) == {"error": "This token is read-only.", "status": 403}


def test_wrong_token(monkeypatch: pytest.MonkeyPatch, api_tokens: dict[str, str]) -> None:
    _use_token(monkeypatch, "not-a-real-secret")
    result = runner.invoke(cli, ["list"])
    assert (result.exit_code, result.stderr) == (1, "Error: Not authenticated. (HTTP 401)\n")
