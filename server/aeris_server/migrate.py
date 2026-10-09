import re
from contextlib import closing
from pathlib import Path

from sqlalchemy import Connection, Engine, text

MIGRATIONS_DIR = Path(__file__).parent.parent / "migrations"
_FILENAME = re.compile(r"^(\d{3})_[a-z0-9_]+\.sql$")
_LOCK_KEY = 0x0AE815  # Arbitrary; serializes concurrent migration runs.


def migration_files(directory: Path = MIGRATIONS_DIR) -> list[Path]:
    """List migration files in order, rejecting misnamed files and duplicate numbers."""
    paths = sorted(directory.glob("*.sql"))
    numbers: set[str] = set()
    for path in paths:
        match = _FILENAME.match(path.name)
        if match is None:
            raise ValueError(f"Bad migration filename: {path.name} (expected NNN_name.sql)")
        if match.group(1) in numbers:
            raise ValueError(f"Duplicate migration number: {match.group(1)}")
        numbers.add(match.group(1))
    return paths


def migrate(engine: Engine, directory: Path = MIGRATIONS_DIR) -> list[str]:
    """Apply pending migrations in order, each in its own transaction. Returns those applied."""
    applied: list[str] = []
    with engine.connect() as connection:
        with connection.begin():
            _lock(connection)
            connection.execute(
                text(
                    "CREATE TABLE IF NOT EXISTS schema_migrations ("
                    " version text PRIMARY KEY,"
                    " applied_at timestamptz NOT NULL DEFAULT now())"
                )
            )
        for path in migration_files(directory):
            version = path.stem
            with connection.begin():
                _lock(connection)
                done = connection.execute(
                    text("SELECT 1 FROM schema_migrations WHERE version = :version"),
                    {"version": version},
                ).first()
                if done:
                    continue
                # Run the file through psycopg with no parameters at all, so it can hold several
                # statements and `%` isn't read as a placeholder. Same connection and transaction.
                with closing(connection.connection.cursor()) as cursor:
                    cursor.execute(path.read_text())
                connection.execute(
                    text("INSERT INTO schema_migrations (version) VALUES (:version)"),
                    {"version": version},
                )
            applied.append(version)
    return applied


def _lock(connection: Connection) -> None:
    connection.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": _LOCK_KEY})
