from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from aeris_server import api

STATIC_DIR = Path(__file__).parent.parent / "static"

app = FastAPI()
app.include_router(api.router)


@app.get("/healthz")
async def healthz() -> dict[str, bool]:
    return {"ok": True}


# On Vercel, files under this mount are served from the CDN, not the function.
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
