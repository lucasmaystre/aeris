"""UI sandbox: aeris on the Neon test branch, seeded with fixture notes, logged in at /dev/login.

    uv run dev/sandbox.py

Uses the `public` schema of `AERIS_TEST_DATABASE_URL` (a branch with no real notes): migrated,
emptied and reseeded on every start, emptied again on exit. Without `AERIS_OPENROUTER_API_KEY`, a
fake embedder (word hashing) stands in for OpenRouter. Also rebuilds the CSS on every change.
Dev only: nothing here is deployed.
"""

import math
import os
import re
import subprocess
import zlib
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, FastAPI, status
from fastapi.responses import RedirectResponse

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"
PORT = 8765
# Not a secret: it only opens this local server, on a branch without real notes.
TOKEN = "sandbox-" + "0" * 32
DIMENSIONS = 256

# Fixture `NN-*.md` is shown as created this long ago, newest first; some were edited since.
# Fixtures beyond this list get older and older.
AGES = [
    (timedelta(minutes=4), None),
    (timedelta(hours=3), timedelta(minutes=20)),
    (timedelta(days=1), None),
    (timedelta(days=2), timedelta(days=1)),
    (timedelta(days=6), None),
    (timedelta(days=13), None),
    (timedelta(days=30), timedelta(days=2)),
    (timedelta(days=61), None),
    (timedelta(days=120), None),
    (timedelta(days=200), timedelta(days=90)),
    (timedelta(days=400), None),
    (timedelta(days=800), None),
]

router = APIRouter(prefix="/dev", include_in_schema=False)


@router.get("/login")
def login() -> RedirectResponse:
    """Log in as the sandbox token, then go to the app."""
    from aeris_server.auth import COOKIE_NAME

    response = RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(COOKIE_NAME, TOKEN, httponly=True, samesite="lax")
    return response


def fake_embed(texts: list[str], **_: object) -> list[list[float]]:
    """Bag-of-words vectors: notes sharing words rank close, roughly like real embeddings."""
    vectors = []
    for text in texts:
        vector = [0.001] * DIMENSIONS  # Never all zeros: cosine distance needs a length.
        for word in re.findall(r"\w+", text.lower()):
            vector[zlib.crc32(word.encode()) % DIMENSIONS] += 1.0
        norm = math.sqrt(sum(x * x for x in vector))
        vectors.append([x / norm for x in vector])
    return vectors


def use_fake_embedder() -> None:
    """Without an OpenRouter key, embed with `fake_embed` (in this process only)."""
    from aeris_server import embeddings

    if not os.environ.get(embeddings.API_KEY_VAR):
        embeddings.embed = fake_embed


def create_app() -> FastAPI:
    """The production app behind the `/dev` routes. Called by uvicorn in its worker process."""
    from aeris_server.app import app as production

    use_fake_embedder()
    sandbox = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    sandbox.include_router(router)
    sandbox.mount("/", production)
    return sandbox


def configure() -> None:
    """Point the app at the test branch's direct endpoint, with the sandbox token."""
    from dotenv import load_dotenv
    from sqlalchemy import make_url

    from aeris_server import db

    load_dotenv(ROOT / ".env")
    url = os.environ.get("AERIS_TEST_DATABASE_URL")
    if not url:
        raise SystemExit(
            "Set AERIS_TEST_DATABASE_URL in .env: the sandbox runs on the test branch."
        )
    direct = make_url(db.to_psycopg_url(url))
    direct = direct.set(host=(direct.host or "").replace("-pooler.", "."))
    os.environ[db.DATABASE_URL_VAR] = direct.render_as_string(hide_password=False)
    os.environ["AERIS_TOKENS"] = f"sandbox:rw:{TOKEN}"


def empty() -> None:
    from sqlalchemy import text

    from aeris_server import db

    with db.engine().begin() as connection:
        connection.execute(text("TRUNCATE note, note_revision, note_embedding RESTART IDENTITY"))


def seed() -> int:
    """Create the fixture notes through the service layer, then backdate them."""
    from sqlalchemy import update

    from aeris_server import db, notes
    from aeris_server.db import Note

    use_fake_embedder()
    now = datetime.now(UTC)
    paths = sorted(FIXTURES.glob("*.md"))
    with db.session() as session:
        for index, path in enumerate(paths):
            created_ago, updated_ago = (
                AGES[index] if index < len(AGES) else (timedelta(days=900 + index), None)
            )
            note = notes.create_note(session, path.read_text())
            created = now - created_ago
            updated = now - updated_ago if updated_ago else created
            session.execute(
                update(Note)
                .where(Note.id == note.id)
                .values(created_at=created, updated_at=updated)
            )
            session.commit()
    return len(paths)


def main() -> None:
    import uvicorn

    from aeris_server import db
    from aeris_server.migrate import migrate

    configure()
    migrate(db.engine())
    empty()
    print(f"Seeded {seed()} notes. Open http://localhost:{PORT}/dev/login")
    css = subprocess.Popen([ROOT / "scripts" / "css.sh", "--watch"], stdin=subprocess.PIPE)
    try:
        uvicorn.run(
            "sandbox:create_app",
            factory=True,
            app_dir=str(Path(__file__).parent),
            port=PORT,
            reload=True,
            reload_dirs=[str(ROOT / "server"), str(Path(__file__).parent)],
        )
    finally:
        css.terminate()
        empty()
        print("Emptied the test branch.")


if __name__ == "__main__":
    main()
