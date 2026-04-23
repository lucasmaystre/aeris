import os
import subprocess
import tempfile
from datetime import datetime

import dateparser
import typer
from sqlalchemy.orm import Session

from aeris.database.engine import engine
from aeris.database.models import Base, Note

app = typer.Typer()


@app.callback()
def main() -> None:
    pass


def _parse_last(value: str) -> datetime:
    result = dateparser.parse(f"{value} ago", settings={"RETURN_AS_TIMEZONE_AWARE": True})
    if result is None:
        typer.echo(f"Could not parse time expression: '{value}'")
        raise typer.Exit(1)
    return result


@app.command()
def add() -> None:
    editor = os.environ.get("EDITOR", "vi")
    fd, path = tempfile.mkstemp(suffix=".txt")
    try:
        os.close(fd)
        subprocess.run([editor, path], check=True)
        with open(path) as f:
            content = f.read().strip()
    finally:
        os.unlink(path)

    if not content:
        typer.echo("Empty note, nothing saved.")
        raise typer.Exit()

    with Session(engine) as session:
        session.add(Note(content=content))
        session.commit()

    typer.echo("Note saved.")


@app.command(name="list")
def list_notes(
    limit: int = typer.Option(30, "--limit"),
    last: str | None = typer.Option(None, "--last"),
) -> None:
    with Session(engine) as session:
        query = session.query(Note).order_by(Note.created_at.asc())
        if last is not None:
            query = query.filter(Note.created_at >= _parse_last(last))
        notes = query.limit(limit).all()

    if not notes:
        return

    id_width = max(len(str(n.id)) for n in notes)
    for note in notes:
        content = note.content.replace("\n", " ")
        if len(content) > 100:
            content = content[:99] + "…"
        created = note.created_at.astimezone().strftime("%Y-%m-%d %H:%M:%S")
        typer.echo(f"{note.id:<{id_width}}  {created}  {content}")


@app.command()
def display(
    id: int | None = typer.Argument(None),
    limit: int = typer.Option(30, "--limit"),
    last: str | None = typer.Option(None, "--last"),
) -> None:
    with Session(engine) as session:
        if id is not None:
            note = session.get(Note, id)
            if note is None:
                typer.echo(f"No note with id {id}.")
                raise typer.Exit(1)
            notes = [note]
        else:
            query = session.query(Note).order_by(Note.created_at.asc())
            if last is not None:
                query = query.filter(Note.created_at >= _parse_last(last))
            notes = query.limit(limit).all()

    for i, note in enumerate(notes):
        created = note.created_at.astimezone().strftime("%Y-%m-%d %H:%M:%S")
        typer.echo(f"# {note.id} {created}")
        typer.echo("")
        typer.echo(note.content.rstrip())
        if i < len(notes) - 1:
            typer.echo("")
            typer.echo("")


@app.command()
def delete(id: int) -> None:
    with Session(engine) as session:
        note = session.get(Note, id)
        if note is None:
            typer.echo(f"No note with id {id}.")
            raise typer.Exit(1)
        session.delete(note)
        session.commit()
    typer.echo("Deleted.")


@app.command(name="reset-db")
def reset_db() -> None:
    confirm = typer.prompt("Type 'reset' to confirm")
    if confirm != "reset":
        typer.echo("Aborted.")
        raise typer.Exit()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    typer.echo("Done.")


if __name__ == "__main__":
    app()
