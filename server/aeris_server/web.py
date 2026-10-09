"""HTML routes for the browser. Thin wrappers around the service layer."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, Literal
from urllib.parse import urlencode, urlsplit

import markdown2
from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from markupsafe import Markup
from sqlalchemy.orm import Session

from aeris_server import auth, notes
from aeris_server.auth import COOKIE_NAME, Token
from aeris_server.db import get_session
from aeris_server.notes import NoteData
from aeris_server.parsing import preview

COOKIE_MAX_AGE = 365 * 24 * 60 * 60
LOCAL_HOSTS = {"localhost", "127.0.0.1"}
CONFLICT_MESSAGE = (
    "This note changed since you opened it. Saving again will overwrite those changes."
)

_MARKDOWN_EXTRAS = ["fenced-code-blocks", "tables", "strike"]
_AGO_UNITS = [
    ("year", 365 * 86400),
    ("month", 30 * 86400),
    ("day", 86400),
    ("hour", 3600),
    ("minute", 60),
]


def ago(moment: datetime, now: datetime | None = None) -> str:
    """Describe how long ago `moment` was, e.g. "3 days ago"."""
    seconds = ((now or datetime.now(UTC)) - moment).total_seconds()
    for unit, size in _AGO_UNITS:
        if seconds >= size:
            count = int(seconds // size)
            return f"{count} {unit}{'' if count == 1 else 's'} ago"
    return "just now"


def time_tag(moment: datetime) -> Markup:
    """A <time> element in UTC; app.js rewrites it into the viewer's timezone."""
    utc = moment.astimezone(UTC)
    return Markup(f'<time datetime="{utc.isoformat()}">{utc:%Y-%m-%d %H:%M} UTC</time>')


def render_markdown(content: str) -> str:
    # Escape raw HTML: agents write notes too, possibly with text copied from the web.
    return markdown2.markdown(content, extras=_MARKDOWN_EXTRAS, safe_mode="escape")


templates = Jinja2Templates(directory=Path(__file__).parent / "templates")
templates.env.filters["ago"] = ago
templates.env.filters["time_tag"] = time_tag
templates.env.filters["preview"] = preview
router = APIRouter()


class LoginRequired(Exception):
    """Raised by web dependencies; the app turns it into a redirect to /login."""


async def handle_login_required(request: Request, error: Exception) -> Response:
    """Send the browser to the login page, which brings it back here afterwards."""
    if request.headers.get("hx-request") == "true":
        # htmx ignores redirects on partial requests, so ask it to navigate instead, coming back
        # to the page that made the request.
        current = urlsplit(request.headers.get("hx-current-url", "")).path or "/"
        return Response(headers={"HX-Redirect": _login_url(current)})
    here = request.url.path + (f"?{request.url.query}" if request.url.query else "")
    return RedirectResponse(_login_url(here), status_code=status.HTTP_303_SEE_OTHER)


def safe_next(value: str) -> str:
    """Only follow local paths after login, so the login page can't redirect to other sites."""
    if value.startswith("/") and not value.startswith("//") and "\\" not in value:
        return value
    return "/"


def _login_url(next_path: str) -> str:
    next_path = safe_next(next_path)
    return "/login" if next_path == "/" else f"/login?{urlencode({'next': next_path})}"


def web_read(request: Request) -> Token:
    """Like `auth.require_read`, but sends unauthenticated browsers to the login page."""
    try:
        return auth.require_read(request)
    except HTTPException as error:
        raise LoginRequired() from error


def web_write(token: Annotated[Token, Depends(web_read)]) -> Token:
    """A logged-in browser with a read-write token; read-only tokens get 403."""
    return auth.require_write(token)


WebReader = Annotated[Token, Depends(web_read)]
SessionDep = Annotated[Session, Depends(get_session)]
READ = [Depends(web_read)]
WRITE = [Depends(web_write)]


@router.get("/login")
def login_form(request: Request, next: str = "/") -> HTMLResponse:
    return templates.TemplateResponse(request, "login.html", {"next": safe_next(next)})


@router.post("/login")
def login(
    request: Request, token: Annotated[str, Form()] = "", next: Annotated[str, Form()] = "/"
) -> Response:
    secret = token.strip()
    if auth.authenticate(secret) is None:
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": "Invalid token.", "next": safe_next(next)},
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    response = RedirectResponse(safe_next(next), status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        COOKIE_NAME,
        secret,
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        # Browsers drop Secure cookies over plain http, which local development uses.
        secure=request.url.hostname not in LOCAL_HOSTS,
        # Lax rather than Strict: links from other sites (mail, chat) still arrive logged in.
        samesite="lax",
    )
    return response


@router.post("/logout")
def logout() -> RedirectResponse:
    response = RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(COOKIE_NAME)
    return response


@router.get("/")
def index(request: Request, token: WebReader) -> HTMLResponse:
    return templates.TemplateResponse(request, "index.html", {"token": token})


@router.get("/n/{note_id}")
def note_page(
    request: Request, token: WebReader, session: SessionDep, note_id: int
) -> HTMLResponse:
    """A note's own page: the whole layout, with the note already open."""
    note = notes.get_note(session, note_id)
    context: dict[str, Any] = {"token": token, "note": note, "missing": note is None}
    if note is not None:
        context.update(rendered_html=render_markdown(note.content or ""), mode="rendered")
    status_code = status.HTTP_200_OK if note else status.HTTP_404_NOT_FOUND
    return templates.TemplateResponse(request, "index.html", context, status_code=status_code)


@router.get("/notes", dependencies=READ)
def note_list(request: Request, session: SessionDep) -> HTMLResponse:
    return _partial(
        request, "note_list.html", notes=notes.list_notes(session), tags=notes.list_tags(session)
    )


# Before `/notes/{note_id}`, which would otherwise match `new`.
@router.get("/notes/new", dependencies=READ)
def new_note_form(request: Request) -> HTMLResponse:
    return _partial(request, "note_form.html")


@router.get("/notes/{note_id}/edit", dependencies=READ)
def edit_note_form(request: Request, session: SessionDep, note_id: int) -> HTMLResponse:
    note = notes.get_note(session, note_id)
    if note is None:
        return _not_found()
    return _form(request, note_id, note.content or "", note.updated_at)


@router.get("/notes/{note_id}", dependencies=READ)
def note_detail(
    request: Request,
    session: SessionDep,
    note_id: int,
    mode: Literal["rendered", "raw"] = "rendered",
) -> HTMLResponse:
    note = notes.get_note(session, note_id)
    if note is None:
        return _not_found()
    return _detail(request, note, mode)


@router.post("/notes", dependencies=WRITE)
def create_note(
    request: Request, session: SessionDep, content: Annotated[str, Form()] = ""
) -> HTMLResponse:
    try:
        note = notes.create_note(session, content)
    except notes.EmptyContent as error:
        return _form(request, None, content, None, error=str(error))
    response = _detail(request, note)
    response.headers["HX-Trigger"] = "noteCreated"
    response.headers["HX-Push-Url"] = f"/n/{note.id}"
    return response


@router.put("/notes/{note_id}", dependencies=WRITE)
def update_note(
    request: Request,
    session: SessionDep,
    note_id: int,
    content: Annotated[str, Form()] = "",
    expected_updated_at: Annotated[datetime | None, Form()] = None,
) -> HTMLResponse:
    try:
        note = notes.update_note(session, note_id, content, expected_updated_at)
    except notes.NoteNotFound:
        return _not_found()
    except notes.EmptyContent as error:
        return _form(request, note_id, content, expected_updated_at, error=str(error))
    except notes.StaleNote as error:
        # Keep the user's text; a second save deliberately overwrites the newer version.
        return _form(
            request,
            note_id,
            content,
            error.current.updated_at,
            error=CONFLICT_MESSAGE,
            conflict=True,
        )
    response = _detail(request, note)
    response.headers["HX-Trigger"] = "noteUpdated"
    return response


@router.delete("/notes/{note_id}", dependencies=WRITE)
def delete_note(request: Request, session: SessionDep, note_id: int) -> HTMLResponse:
    try:
        notes.delete_note(session, note_id)
    except notes.NoteNotFound:
        return _not_found()
    response = _partial(request, "note_deleted.html", note_id=note_id)
    response.headers["HX-Trigger"] = "noteDeleted"
    response.headers["HX-Push-Url"] = "/"
    return response


def _partial(request: Request, name: str, **context: Any) -> HTMLResponse:
    return templates.TemplateResponse(request, f"partials/{name}", context)


def _detail(
    request: Request, note: NoteData, mode: Literal["rendered", "raw"] = "rendered"
) -> HTMLResponse:
    content = note.content or ""
    rendered = render_markdown(content) if mode == "rendered" else None
    return _partial(request, "note_detail.html", note=note, rendered_html=rendered, mode=mode)


def _form(
    request: Request,
    note_id: int | None,
    content: str,
    expected_updated_at: datetime | None,
    error: str | None = None,
    conflict: bool = False,
) -> HTMLResponse:
    return _partial(
        request,
        "note_form.html",
        note_id=note_id,
        content=content,
        expected_updated_at=expected_updated_at,
        error=error,
        conflict=conflict,
    )


def _not_found() -> HTMLResponse:
    return HTMLResponse(
        "<p class='p-6 text-red-600'>Note not found.</p>", status_code=status.HTTP_404_NOT_FOUND
    )
