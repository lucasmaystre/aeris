import json
import os
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

import arrow
import typer
from sqlalchemy import text
from sqlalchemy.orm import Session

from aeris import __version__
from aeris.database.engine import engine
from aeris.database.models import Base, Note

app = typer.Typer()


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(False, "--version", callback=_version_callback, is_eager=True),
) -> None:
    pass


def _parse_last(value: str) -> datetime:
    try:
        return arrow.now().dehumanize(f"{value} ago").datetime
    except Exception:
        typer.echo(f"Could not parse time expression: '{value}'")
        raise typer.Exit(1)


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
        query = session.query(Note).filter(Note.deleted == False).order_by(Note.created_at.asc())
        if last is not None:
            query = query.filter(Note.created_at >= _parse_last(last))
        notes = query.limit(limit).all()

    if not notes:
        return

    id_width = max(len(str(n.id)) for n in notes)
    terminal_width = shutil.get_terminal_size().columns
    content_limit = max(10, min(100, terminal_width - id_width - 23))
    for note in notes:
        content = note.content.replace("\n", " ")
        if len(content) > content_limit:
            content = content[:content_limit - 1] + "…"
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
            if note is None or note.deleted:
                typer.echo(f"No note with id {id}.")
                raise typer.Exit(1)
            notes = [note]
        else:
            query = session.query(Note).filter(Note.deleted == False).order_by(Note.created_at.asc())
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
        note.deleted = True
        session.commit()
    typer.echo("Deleted.")


@app.command()
def export(path: Path | None = typer.Argument(None)) -> None:
    if path is None:
        path = Path(f"aeris-export-{datetime.now().strftime('%Y%m%d-%H%M%S')}.jsonl")
    with Session(engine) as session:
        notes = session.query(Note).filter(Note.deleted == False).order_by(Note.id.asc()).all()
    with open(path, "w") as f:
        for note in notes:
            f.write(
                json.dumps(
                    {
                        "id": note.id,
                        "created_at": note.created_at.isoformat(),
                        "updated_at": note.updated_at.isoformat(),
                        "content": note.content,
                    }
                )
                + "\n"
            )
    typer.echo(f"Exported {len(notes)} notes to {path}.")


@app.command()
def web(port: int = typer.Option(8822, "--port")) -> None:
    import uvicorn

    uvicorn.run("aeris.web.main:app", host="127.0.0.1", port=port)


@app.command(name="reset-db")
def reset_db(data: Path | None = typer.Option(None, "--data")) -> None:
    if data is not None and not data.exists():
        typer.echo(f"File not found: {data}")
        raise typer.Exit(1)
    confirm = typer.prompt("Type 'reset' to confirm")
    if confirm != "reset":
        typer.echo("Aborted.")
        raise typer.Exit()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    if data is not None:
        with open(data) as f:
            records = [json.loads(line) for line in f if line.strip()]
        with Session(engine) as session:
            for record in records:
                session.add(
                    Note(
                        id=record["id"],
                        created_at=datetime.fromisoformat(record["created_at"]),
                        updated_at=datetime.fromisoformat(record["updated_at"]),
                        content=record["content"],
                    )
                )
            session.flush()
            session.execute(text("SELECT setval(pg_get_serial_sequence('note', 'id'), MAX(id)) FROM note"))
            session.commit()
        typer.echo(f"Loaded {len(records)} notes.")
    typer.echo("Done.")


if __name__ == "__main__":
    app()
