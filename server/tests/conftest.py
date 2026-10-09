import os
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from dotenv import load_dotenv
from sqlalchemy import URL, Engine, create_engine, make_url, text
from sqlalchemy.pool import NullPool

from aeris_server import db
from aeris_server.migrate import migrate

TEST_DATABASE_URL_VAR = "AERIS_TEST_DATABASE_URL"
DB_FIXTURES = {"database", "empty_database"}

load_dotenv(Path(__file__).parents[2] / ".env")


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Mark every test that uses a database fixture with `db`."""
    for item in items:
        if DB_FIXTURES & set(getattr(item, "fixturenames", ())):
            item.add_marker(pytest.mark.db)


def _direct_url() -> URL:
    url = os.environ.get(TEST_DATABASE_URL_VAR)
    if not url:
        pytest.skip(f"{TEST_DATABASE_URL_VAR} is not set")
    # Neon's pooler rejects the `options` startup parameter, so use the direct endpoint.
    direct = make_url(db.to_psycopg_url(url))
    return direct.set(host=(direct.host or "").replace("-pooler.", "."))


def _scoped(url: URL, schema: str) -> str:
    scoped = url.update_query_dict({"options": f"-csearch_path={schema},public"})
    return scoped.render_as_string(hide_password=False)


def _schema(url: URL) -> Iterator[str]:
    """Create a throwaway schema on the test branch, yield its name, then drop it."""
    schema = f"test_{uuid.uuid4().hex[:12]}"
    admin = create_engine(url, poolclass=NullPool)
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    try:
        yield schema
    finally:
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


def _use(monkeypatch: pytest.MonkeyPatch, url: str) -> Iterator[None]:
    monkeypatch.setenv(db.DATABASE_URL_VAR, url)
    db.engine.cache_clear()
    yield
    db.engine.cache_clear()


@pytest.fixture(scope="session")
def _migrated_engine() -> Iterator[Engine]:
    """One migrated schema shared by the whole test run, behind a pooled engine.

    Unlike the app's `NullPool` engine, this reuses connections: opening one to Neon costs ~100 ms.
    """
    url = _direct_url()
    for schema in _schema(url):
        engine = create_engine(_scoped(url, schema))
        migrate(engine)
        yield engine
        engine.dispose()


@pytest.fixture
def database(_migrated_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the app at the shared migrated schema, emptied first."""
    monkeypatch.setattr(db, "engine", lambda: _migrated_engine)
    with _migrated_engine.begin() as connection:
        tables = connection.execute(
            text(
                "SELECT quote_ident(tablename) FROM pg_tables"
                " WHERE schemaname = current_schema() AND tablename <> 'schema_migrations'"
            )
        ).scalars()
        connection.execute(text(f"TRUNCATE {', '.join(tables)} RESTART IDENTITY CASCADE"))


@pytest.fixture
def empty_database(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Point the app at a fresh, empty schema, for testing migrations themselves."""
    url = _direct_url()
    for schema in _schema(url):
        yield from _use(monkeypatch, _scoped(url, schema))
