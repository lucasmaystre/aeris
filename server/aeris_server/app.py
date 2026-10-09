from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from aeris_server import api, web

STATIC_DIR = Path(__file__).parent.parent / "static"

app = FastAPI()
app.include_router(api.router)
app.include_router(web.router)
app.add_exception_handler(web.LoginRequired, web.handle_login_required)


@app.get("/healthz")
async def healthz() -> dict[str, bool]:
    return {"ok": True}


# On Vercel, files under this mount are served from the CDN, not the function.
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
