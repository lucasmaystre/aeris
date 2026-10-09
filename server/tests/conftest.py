import os
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from dotenv import load_dotenv
from sqlalchemy import create_engine, make_url, text
from sqlalchemy.pool import NullPool

from aeris_server import db
from aeris_server.migrate import migrate

TEST_DATABASE_URL_VAR = "AERIS_TEST_DATABASE_URL"

load_dotenv(Path(__file__).parents[2] / ".env")


@pytest.fixture
def empty_database(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """Point the app at a fresh, empty schema on the test branch; drop it afterwards.

    Skips the test if no test database is configured. Yields the schema name.
    """
    url = os.environ.get(TEST_DATABASE_URL_VAR)
    if not url:
        pytest.skip(f"{TEST_DATABASE_URL_VAR} is not set")
    # Neon's pooler rejects the `options` startup parameter, so use the direct endpoint.
    direct = make_url(db.to_psycopg_url(url))
    direct = direct.set(host=(direct.host or "").replace("-pooler.", "."))
    schema = f"test_{uuid.uuid4().hex[:12]}"

    admin = create_engine(direct, poolclass=NullPool)
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    scoped = direct.update_query_dict({"options": f"-csearch_path={schema},public"})
    monkeypatch.setenv(db.DATABASE_URL_VAR, scoped.render_as_string(hide_password=False))
    db.engine.cache_clear()
    try:
        yield schema
    finally:
        db.engine.cache_clear()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


@pytest.fixture
def database(empty_database: str) -> str:
    """Like `empty_database`, with all migrations applied."""
    migrate(db.engine())
    return empty_database
