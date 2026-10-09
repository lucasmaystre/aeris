"""The `aeris` command: notes from the terminal, for humans and agents (`--json`)."""

import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any

import typer

from aeris_cli.client import AerisError, Client
from aeris_cli.config import ConfigError, load_config

app = typer.Typer(no_args_is_help=True, add_completion=False)

JsonOption = Annotated[bool, typer.Option("--json", help="Print the API's JSON response.")]
MessageOption = Annotated[
    str | None,
    typer.Option("--message", "-m", help="The text. Otherwise read from stdin or your editor."),
]
CONFLICT = 409
NO_TEXT = "No text to save: pass -m TEXT, pipe text in, or run in a terminal to use your editor."

_DURATION = re.compile(r"\s*(\d+)\s*(m|mins?|minutes?|h|hours?|d|days?|w|weeks?)\s*", re.IGNORECASE)
_UNITS = {"m": "minutes", "h": "hours", "d": "days", "w": "weeks"}


class Order(StrEnum):
    created = "created"
    updated = "updated"


def make_client() -> Client:
    return Client(load_config())


def parse_since(value: str, now: datetime | None = None) -> datetime:
    """Parse `--last`: a duration like `2 days` or `3h`, or an ISO date or datetime."""
    if match := _DURATION.fullmatch(value):
        unit = _UNITS[match.group(2)[0].lower()]
        return (now or datetime.now().astimezone()) - timedelta(**{unit: int(match.group(1))})
    try:
        return datetime.fromisoformat(value.strip()).astimezone()
    except ValueError:
        raise typer.BadParameter(
            f"{value!r}: use a duration like '2 days' or '3h', or a date like 2026-10-01."
        ) from None


@app.command("list")
def list_notes(
    limit: Annotated[int, typer.Option(min=1, help="How many notes to show.")] = 30,
    last: Annotated[
        str | None, typer.Option(help="Only notes from the last '2 days', '3h'...")
    ] = None,
    tag: Annotated[
        str | None, typer.Option(help="Only notes with this tag or its children.")
    ] = None,
    order: Annotated[Order, typer.Option(help="Sort by creation or last update.")] = Order.created,
    json_output: JsonOption = False,
) -> None:
    """List notes, newest first."""
    since = parse_since(last) if last is not None else None
    with _errors():
        data = make_client().list_notes(limit=limit, since=since, tag=tag, order=order.value)
    if json_output:
        _print_json(data)
        return
    width = _id_width(data["notes"])
    for note in data["notes"]:
        typer.echo(_summary(note, width, f"{order.value}_at"))


@app.command()
def search(
    query: Annotated[list[str], typer.Argument(help="Words to find, as one phrase.")],
    tag: Annotated[
        str | None, typer.Option(help="Only notes with this tag or its children.")
    ] = None,
    limit: Annotated[int, typer.Option(min=1, help="How many notes to show.")] = 30,
    json_output: JsonOption = False,
) -> None:
    """Find notes containing a phrase, ignoring case and accents."""
    phrase = " ".join(query)
    with _errors():
        data = make_client().search(phrase, tag=tag, limit=limit)
    if json_output:
        _print_json(data)
        return
    if not data["hits"]:
        typer.echo(f"No notes match {phrase!r}.", err=True)
    width = _id_width(data["hits"])
    indent = " " * (width + 20)  # Lines the snippet up with the title.
    for hit in data["hits"]:
        typer.echo(_summary(hit, width, "created_at"))
        typer.echo(indent + hit["snippet"])


@app.command()
def tags(json_output: JsonOption = False) -> None:
    """List tags with how many notes carry each."""
    with _errors():
        data = make_client().list_tags()
    if json_output:
        _print_json(data)
        return
    width = max((len(str(tag["count"])) for tag in data["tags"]), default=0)
    for tag in data["tags"]:
        typer.echo(f"{tag['count']:>{width}}  #{tag['tag']}")


@app.command()
def show(
    ids: Annotated[list[int], typer.Argument(help="One or more note IDs.")],
    json_output: JsonOption = False,
) -> None:
    """Show notes in full."""
    with _errors():
        data = make_client().get_notes(ids)
    if json_output:
        _print_json(data)
    else:
        for i, note in enumerate(data["notes"]):
            if i > 0:
                typer.echo("\n")
            typer.echo(f"# {note['id']} {_local(note['created_at'])}\n")
            typer.echo(note["content"].rstrip())
    for note_id in data["missing"]:
        typer.echo(f"No note with id {note_id}.", err=True)
    if data["missing"]:
        raise typer.Exit(1)


@app.command()
def add(message: MessageOption = None, json_output: JsonOption = False) -> None:
    """Create a note."""
    content = _input_text(message)
    with _errors():
        note = make_client().create_note(content)
    if json_output:
        _print_json(note)
    else:
        typer.echo(f"Created note {note['id']}.")


@app.command()
def append(
    note_id: Annotated[int, typer.Argument(help="The note to add to.")],
    message: MessageOption = None,
    json_output: JsonOption = False,
) -> None:
    """Add text to the end of a note, as a new paragraph."""
    text = _input_text(message)
    with _errors():
        note = make_client().append_note(note_id, text)
    if json_output:
        _print_json(note)
    else:
        typer.echo(f"Appended to note {note_id}.")


@app.command()
def edit(
    note_id: Annotated[int, typer.Argument(help="The note to edit.")],
    stdin: Annotated[
        bool, typer.Option("--stdin", help="Read the new content from stdin, not your editor.")
    ] = False,
    expected_updated_at: Annotated[
        str | None,
        typer.Option(
            help="With --stdin: fail if the note changed after this time (its updated_at)."
        ),
    ] = None,
    json_output: JsonOption = False,
) -> None:
    """Replace a note's content, in your editor or from stdin."""
    if expected_updated_at is not None and not stdin:
        raise typer.BadParameter("only with --stdin.", param_hint="--expected-updated-at")
    if stdin:
        content = sys.stdin.read()
        if not content.strip():
            typer.echo("Error: No text to save: pipe the new content in.", err=True)
            raise typer.Exit(1)
        with _errors():
            note = make_client().update_note(note_id, content, expected_updated_at)
    else:
        if not _interactive():
            typer.echo("Error: Not in a terminal: use --stdin to pass the new content.", err=True)
            raise typer.Exit(1)
        note = _edit_in_editor(note_id)
    if json_output:
        _print_json(note)
    else:
        typer.echo(f"Updated note {note_id}.")


@app.command()
def delete(note_id: Annotated[int, typer.Argument(help="The note to delete.")]) -> None:
    """Delete a note."""
    with _errors():
        make_client().delete_note(note_id)
    typer.echo(f"Deleted note {note_id}.")


def edit_in_editor(initial: str = "") -> str:
    """Open `$VISUAL` or `$EDITOR` (else vi) on a temporary file, and return what was saved."""
    editor = os.environ.get("VISUAL") or os.environ.get("EDITOR") or "vi"
    fd, path = tempfile.mkstemp(suffix=".md")
    try:
        with os.fdopen(fd, "w") as file:
            file.write(initial)
        subprocess.run([*shlex.split(editor), path], check=True)
        return Path(path).read_text()
    finally:
        os.unlink(path)


def _edit_in_editor(note_id: int) -> dict[str, Any]:
    """Edit a note's current content in the editor and save it, guarding against conflicts."""
    client = make_client()
    with _errors():
        current = client.get_note(note_id)
    content = _run_editor(current["content"])
    if not content.strip():
        typer.echo("Empty note, nothing saved.")
        raise typer.Exit(0)
    if content.strip() == current["content"].strip():
        typer.echo("No changes.")
        raise typer.Exit(0)
    try:
        return client.update_note(note_id, content, current["updated_at"])
    except AerisError as error:
        if error.status != CONFLICT:
            typer.echo(f"Error: {error}", err=True)
            raise typer.Exit(1) from error
        fd, draft = tempfile.mkstemp(prefix=f"aeris-note-{note_id}-", suffix=".md")
        with os.fdopen(fd, "w") as file:
            file.write(content)
        typer.echo(
            f"Error: Note {note_id} changed while you were editing; nothing saved. "
            f"Your text is in {draft}",
            err=True,
        )
        raise typer.Exit(1) from error


def _run_editor(initial: str = "") -> str:
    try:
        return edit_in_editor(initial)
    except (OSError, subprocess.CalledProcessError) as error:
        typer.echo(f"Error: the editor failed ({error}); nothing saved.", err=True)
        raise typer.Exit(1) from error


def _interactive() -> bool:
    return sys.stdin.isatty()


def _input_text(message: str | None) -> str:
    """Text from `-m`, else piped stdin, else the editor in an interactive terminal.

    Exits without saving if the text is empty: quietly if the user emptied the editor, with an
    error otherwise (e.g. an agent that passed nothing).
    """
    if message is not None:
        text = message
    elif not _interactive():
        text = sys.stdin.read()
    else:
        text = _run_editor()
        if not text.strip():
            typer.echo("Empty note, nothing saved.")
            raise typer.Exit(0)
    if not text.strip():
        typer.echo(f"Error: {NO_TEXT}", err=True)
        raise typer.Exit(1)
    return text


@contextmanager
def _errors() -> Iterator[None]:
    try:
        yield
    except (ConfigError, AerisError) as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(1) from error


def _id_width(notes: list[dict[str, Any]]) -> int:
    return max((len(str(note["id"])) for note in notes), default=0)


def _summary(note: dict[str, Any], width: int, timestamp_field: str) -> str:
    """One line per note: ID, local time, title, tags."""
    tags = "".join(f"  #{tag}" for tag in note["tags"])
    title = note["title"] or "(untitled)"
    return f"{note['id']:>{width}}  {_local(note[timestamp_field])}  {title}{tags}"


def _local(timestamp: str) -> str:
    return f"{datetime.fromisoformat(timestamp).astimezone():%Y-%m-%d %H:%M}"


def _print_json(data: Any) -> None:
    typer.echo(json.dumps(data, indent=2, ensure_ascii=False))
