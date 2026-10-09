"""HTML routes for the browser. Thin wrappers around the service layer."""

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from aeris_server import auth
from aeris_server.auth import COOKIE_NAME, Token

COOKIE_MAX_AGE = 365 * 24 * 60 * 60
LOCAL_HOSTS = {"localhost", "127.0.0.1"}

templates = Jinja2Templates(directory=Path(__file__).parent / "templates")
router = APIRouter()


class LoginRequired(Exception):
    """Raised by web dependencies; the app turns it into a redirect to /login."""


async def handle_login_required(request: Request, error: Exception) -> Response:
    # htmx ignores redirects on partial requests, so ask it to navigate instead.
    if request.headers.get("hx-request") == "true":
        return Response(headers={"HX-Redirect": "/login"})
    return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)


def web_read(request: Request) -> Token:
    """Like `auth.require_read`, but sends unauthenticated browsers to the login page."""
    try:
        return auth.require_read(request)
    except HTTPException as error:
        raise LoginRequired() from error


WebReader = Annotated[Token, Depends(web_read)]


@router.get("/login")
def login_form(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "login.html")


@router.post("/login")
def login(request: Request, token: Annotated[str, Form()] = "") -> Response:
    secret = token.strip()
    if auth.authenticate(secret) is None:
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": "Invalid token."},
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    response = RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
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
def home(request: Request, token: WebReader) -> HTMLResponse:
    return templates.TemplateResponse(request, "home.html", {"token": token})
