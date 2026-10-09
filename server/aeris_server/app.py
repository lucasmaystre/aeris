import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from aeris_server import api, web

STATIC_DIR = Path(__file__).parent.parent / "static"

# Interactive API docs locally only: production shouldn't advertise its endpoints.
ON_VERCEL = bool(os.environ.get("VERCEL"))

app = FastAPI(
    docs_url=None if ON_VERCEL else "/docs",
    redoc_url=None if ON_VERCEL else "/redoc",
    openapi_url=None if ON_VERCEL else "/openapi.json",
)
app.include_router(api.router)
app.include_router(web.router)
app.add_exception_handler(web.LoginRequired, web.handle_login_required)


@app.get("/healthz")
async def healthz() -> dict[str, bool]:
    return {"ok": True}


# On Vercel, files under this mount are served from the CDN, not the function.
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
