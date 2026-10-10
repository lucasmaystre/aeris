from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from aeris_server import api, web

STATIC_DIR = Path(__file__).parent.parent / "static"

# FastAPI's own docs routes are public; ours below require login, like the web UI.
app = FastAPI(title="aeris", docs_url=None, redoc_url=None, openapi_url=None)
app.include_router(api.router)
app.include_router(web.router)
app.add_exception_handler(web.LoginRequired, web.handle_login_required)

LOGGED_IN = [Depends(web.web_read)]


@app.get("/openapi.json", dependencies=LOGGED_IN, include_in_schema=False)
def openapi() -> dict[str, Any]:
    return app.openapi()


@app.get("/docs", dependencies=LOGGED_IN, include_in_schema=False)
def docs() -> HTMLResponse:
    """Swagger UI. "Try it out" sends the login cookie, or a token set with "Authorize"."""
    return get_swagger_ui_html(openapi_url="/openapi.json", title="aeris API")


@app.get("/healthz")
async def healthz() -> dict[str, bool]:
    return {"ok": True}


# On Vercel, files under this mount are served from the CDN, not the function.
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
