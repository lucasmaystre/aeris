from pathlib import Path

import arrow
import markdown2
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from aeris.database.engine import engine
from aeris.database.models import Note

app = FastAPI()

BASE_DIR = Path(__file__).parent
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")

PAGE_SIZE = 50

_MARKDOWN_EXTRAS = ["fenced-code-blocks", "tables", "strike"]


def _render(content: str) -> str:
    return markdown2.markdown(content, extras=_MARKDOWN_EXTRAS)


def _excerpt(content: str) -> str:
    flat = " ".join(content.split())
    return flat[:150] + "…" if len(flat) > 150 else flat


templates.env.filters["elapsed"] = lambda dt: arrow.get(dt).humanize()
templates.env.filters["excerpt"] = _excerpt


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "index.html")


@app.get("/notes", response_class=HTMLResponse)
async def note_list(request: Request, offset: int = 0) -> HTMLResponse:
    with Session(engine) as session:
        notes = (
            session.query(Note)
            .filter(Note.deleted == False)
            .order_by(Note.created_at.desc())
            .offset(offset)
            .limit(PAGE_SIZE)
            .all()
        )
    has_more = len(notes) == PAGE_SIZE
    return templates.TemplateResponse(
        request,
        "partials/note_list.html",
        {"notes": notes, "offset": offset + PAGE_SIZE, "has_more": has_more},
    )


@app.get("/notes/new", response_class=HTMLResponse)
async def new_note_form(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "partials/note_form.html")


@app.get("/notes/{note_id}/edit", response_class=HTMLResponse)
async def edit_note_form(request: Request, note_id: int) -> HTMLResponse:
    with Session(engine) as session:
        note = session.get(Note, note_id)
    if note is None or note.deleted:
        return HTMLResponse("<p class='p-6 text-red-600'>Note not found.</p>", status_code=404)
    return templates.TemplateResponse(request, "partials/note_form.html", {"note": note})


@app.get("/notes/{note_id}", response_class=HTMLResponse)
async def note_detail(request: Request, note_id: int, mode: str = "rendered") -> HTMLResponse:
    with Session(engine) as session:
        note = session.get(Note, note_id)
    if note is None or note.deleted:
        return HTMLResponse("<p class='p-6 text-red-600'>Note not found.</p>", status_code=404)
    rendered_html = _render(note.content) if mode == "rendered" else None
    return templates.TemplateResponse(
        request,
        "partials/note_detail.html",
        {"note": note, "rendered_html": rendered_html, "mode": mode},
    )


@app.post("/notes", response_class=HTMLResponse)
async def create_note(request: Request, content: str = Form(...)) -> HTMLResponse:
    content = content.strip()
    if not content:
        return templates.TemplateResponse(
            request, "partials/note_form.html", {"error": "Note content cannot be empty."}
        )
    with Session(engine) as session:
        note = Note(content=content)
        session.add(note)
        session.commit()
        session.refresh(note)
        note_id = note.id

    with Session(engine) as session:
        note = session.get(Note, note_id)

    response = templates.TemplateResponse(
        request,
        "partials/note_detail.html",
        {"note": note, "rendered_html": _render(note.content), "mode": "rendered"},
    )
    response.headers["HX-Trigger"] = "noteCreated"
    return response


@app.put("/notes/{note_id}", response_class=HTMLResponse)
async def update_note(request: Request, note_id: int, content: str = Form(...)) -> HTMLResponse:
    content = content.strip()
    with Session(engine) as session:
        note = session.get(Note, note_id)
        if note is None or note.deleted:
            return HTMLResponse("<p class='p-6 text-red-600'>Note not found.</p>", status_code=404)
        if not content:
            return templates.TemplateResponse(
                request,
                "partials/note_form.html",
                {"note": note, "error": "Note content cannot be empty."},
            )
        note.content = content
        session.commit()
        session.refresh(note)
    response = templates.TemplateResponse(
        request,
        "partials/note_detail.html",
        {"note": note, "rendered_html": _render(note.content), "mode": "rendered"},
    )
    response.headers["HX-Trigger"] = "noteUpdated"
    return response
