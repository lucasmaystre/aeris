import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from dotenv import load_dotenv

from aeris_server import db

TEST_DATABASE_URL_VAR = "AERIS_TEST_DATABASE_URL"

load_dotenv(Path(__file__).parents[2] / ".env")


@pytest.fixture
def database(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Point the app at the test database, or skip the test if none is configured."""
    url = os.environ.get(TEST_DATABASE_URL_VAR)
    if not url:
        pytest.skip(f"{TEST_DATABASE_URL_VAR} is not set")
    monkeypatch.setenv(db.DATABASE_URL_VAR, url)
    db.engine.cache_clear()
    yield
    db.engine.cache_clear()
