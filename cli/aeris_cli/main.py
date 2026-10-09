"""The `aeris` command: notes from the terminal, for humans and agents (`--json`)."""

import json
import re
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Annotated, Any

import typer

from aeris_cli.client import AerisError, Client
from aeris_cli.config import ConfigError, load_config

app = typer.Typer(no_args_is_help=True, add_completion=False)

JsonOption = Annotated[bool, typer.Option("--json", help="Print the API's JSON response.")]

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
    notes = data["notes"]
    width = max((len(str(note["id"])) for note in notes), default=0)
    for note in notes:
        when = _local(note[f"{order.value}_at"])
        tags = "".join(f"  #{tag}" for tag in note["tags"])
        typer.echo(f"{note['id']:>{width}}  {when}  {note['title'] or '(untitled)'}{tags}")


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


@contextmanager
def _errors() -> Iterator[None]:
    try:
        yield
    except (ConfigError, AerisError) as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(1) from error


def _local(timestamp: str) -> str:
    return f"{datetime.fromisoformat(timestamp).astimezone():%Y-%m-%d %H:%M}"


def _print_json(data: Any) -> None:
    typer.echo(json.dumps(data, indent=2, ensure_ascii=False))
