from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

STATIC_DIR = Path(__file__).parent.parent / "static"

app = FastAPI()


@app.get("/healthz")
async def healthz() -> dict[str, bool]:
    return {"ok": True}


# On Vercel, files under this mount are served from the CDN, not the function.
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
