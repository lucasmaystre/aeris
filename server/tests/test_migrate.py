from pathlib import Path

import pytest
from sqlalchemy import text

from aeris_server import db
from aeris_server.admin import main
from aeris_server.migrate import migrate, migration_files


def _tables() -> set[str]:
    with db.engine().connect() as connection:
        rows = connection.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname = current_schema()")
        )
        return set(rows.scalars())


def _versions() -> list[str]:
    with db.engine().connect() as connection:
        rows = connection.execute(text("SELECT version FROM schema_migrations ORDER BY version"))
        return list(rows.scalars())


@pytest.mark.usefixtures("empty_database")
def test_migrate_empty_database() -> None:
    assert migrate(db.engine()) == ["001_baseline"]
    assert _tables() == {"note", "schema_migrations"}
    assert _versions() == ["001_baseline"]


@pytest.mark.usefixtures("database")
def test_migrate_is_idempotent() -> None:
    assert migrate(db.engine()) == []


@pytest.mark.usefixtures("empty_database")
def test_baseline_keeps_existing_notes() -> None:
    # Production had the `note` table before migrations existed.
    with db.engine().begin() as connection:
        connection.execute(text("CREATE TABLE note (id serial PRIMARY KEY, content text NOT NULL)"))
        connection.execute(text("INSERT INTO note (content) VALUES ('hello')"))
    assert migrate(db.engine()) == ["001_baseline"]
    with db.engine().connect() as connection:
        assert connection.execute(text("SELECT content FROM note")).scalars().all() == ["hello"]


@pytest.mark.usefixtures("empty_database")
def test_failed_migration_rolls_back(tmp_path: Path) -> None:
    (tmp_path / "001_ok.sql").write_text("CREATE TABLE a (s text DEFAULT '100%');\nSELECT 1;")
    (tmp_path / "002_bad.sql").write_text("CREATE TABLE b (id int);\nSELECT 1 / 0;")
    with pytest.raises(Exception, match="division by zero"):
        migrate(db.engine(), tmp_path)
    assert _tables() == {"a", "schema_migrations"}
    assert _versions() == ["001_ok"]


@pytest.mark.parametrize("names", [["1_short.sql"], ["001-dash.sql"], ["001_a.sql", "001_b.sql"]])
def test_migration_files_rejects_bad_names(tmp_path: Path, names: list[str]) -> None:
    for name in names:
        (tmp_path / name).write_text("")
    with pytest.raises(ValueError):
        migration_files(tmp_path)


def test_migration_files_are_ordered() -> None:
    paths = migration_files()
    assert [p.name for p in paths] == sorted(p.name for p in paths)
    assert paths[0].name == "001_baseline.sql"


@pytest.mark.usefixtures("database")
def test_admin_migrate(capsys: pytest.CaptureFixture[str]) -> None:
    main(["migrate"])
    assert capsys.readouterr().out == "Up to date.\n"
