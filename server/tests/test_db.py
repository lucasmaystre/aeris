import pytest
from sqlalchemy import text

from aeris_server import db


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        (
            "postgresql://u:p@host/db?sslmode=require",
            "postgresql+psycopg://u:p@host/db?sslmode=require",
        ),
        ("postgres://u:p@host/db", "postgresql+psycopg://u:p@host/db"),
        ("postgresql+psycopg://u:p@host/db", "postgresql+psycopg://u:p@host/db"),
    ],
)
def test_to_psycopg_url(url: str, expected: str) -> None:
    assert db.to_psycopg_url(url) == expected


def test_database_url_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(db.DATABASE_URL_VAR, raising=False)
    with pytest.raises(RuntimeError, match=db.DATABASE_URL_VAR):
        db.database_url()


@pytest.mark.usefixtures("database")
def test_connect() -> None:
    with db.session() as session:
        assert session.execute(text("SELECT 1")).scalar_one() == 1
