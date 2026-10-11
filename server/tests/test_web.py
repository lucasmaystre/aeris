from datetime import UTC, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from aeris_server import db, notes
from aeris_server.app import app
from aeris_server.auth import COOKIE_NAME
from aeris_server.web import CONFLICT_MESSAGE, ago, render_markdown, safe_next, time_tag

pytestmark = pytest.mark.usefixtures("api_tokens")


def _client(base_url: str = "https://aeris.example") -> TestClient:
    return TestClient(app, base_url=base_url, follow_redirects=False)


# Redirects to the login page.


def test_page_redirects_to_login() -> None:
    response = _client().get("/")
    assert (response.status_code, response.headers["location"]) == (303, "/login")


def test_htmx_request_redirects_to_login() -> None:
    response = _client().get("/", headers={"HX-Request": "true"})
    assert (response.status_code, response.headers["hx-redirect"]) == (200, "/login")
    headers = {"HX-Request": "true", "HX-Current-URL": "https://aeris.example/n/7"}
    response = _client().get("/notes/7", headers=headers)
    assert response.headers["hx-redirect"] == "/login?next=%2Fn%2F7"


def test_page_redirect_remembers_where_to_return() -> None:
    response = _client().get("/n/7")
    assert response.headers["location"] == "/login?next=%2Fn%2F7"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("/n/7", "/n/7"),
        ("/?x=1", "/?x=1"),
        ("", "/"),
        ("n/7", "/"),
        ("//evil.example", "/"),
        ("/\\evil.example", "/"),
        ("https://evil.example/", "/"),
    ],
)
def test_safe_next(value: str, expected: str) -> None:
    assert safe_next(value) == expected


def test_login_returns_to_next(api_tokens: dict[str, str]) -> None:
    form = _client().get("/login?next=/n/7").text
    assert '<input type="hidden" name="next" value="/n/7">' in form
    data = {"token": api_tokens["rw"], "next": "/n/7"}
    assert _client().post("/login", data=data).headers["location"] == "/n/7"
    data["next"] = "//evil.example"
    assert _client().post("/login", data=data).headers["location"] == "/"


def test_invalid_cookie_redirects_to_login() -> None:
    client = TestClient(app, cookies={COOKIE_NAME: "wrong"}, follow_redirects=False)
    assert client.get("/").status_code == 303


# Login and logout.


def test_login_form() -> None:
    response = _client().get("/login")
    assert response.status_code == 200
    assert 'name="token"' in response.text
    assert "New note" not in response.text and "Log out" not in response.text


def test_login_invalid_token() -> None:
    response = _client().post("/login", data={"token": "wrong"})
    assert response.status_code == 401
    assert "Invalid token." in response.text
    assert "set-cookie" not in response.headers


def test_login(api_tokens: dict[str, str]) -> None:
    client = _client()
    response = client.post("/login", data={"token": f"  {api_tokens['ro']}  "})
    assert (response.status_code, response.headers["location"]) == (303, "/")
    cookie = response.headers["set-cookie"]
    assert cookie.startswith(f"{COOKIE_NAME}={api_tokens['ro']};")
    for attribute in ["HttpOnly", "Max-Age=31536000", "Path=/", "SameSite=lax", "Secure"]:
        assert attribute in cookie
    # The client kept the cookie, so the index page now works, with the logged-in top bar.
    index = client.get("/")
    assert index.status_code == 200
    assert "Log out" in index.text


def test_login_on_localhost_is_not_secure(api_tokens: dict[str, str]) -> None:
    response = _client("http://localhost:8000").post("/login", data={"token": api_tokens["rw"]})
    assert response.status_code == 303
    assert "Secure" not in response.headers["set-cookie"]


def test_logout(api_tokens: dict[str, str]) -> None:
    client = _client()
    client.post("/login", data={"token": api_tokens["rw"]})
    response = client.post("/logout")
    assert (response.status_code, response.headers["location"]) == (303, "/login")
    assert f'{COOKIE_NAME}="";' in response.headers["set-cookie"]
    assert client.get("/").status_code == 303


# Helpers.


@pytest.mark.parametrize(
    ("delta", "expected"),
    [
        (timedelta(seconds=30), "just now"),
        (timedelta(minutes=1), "1 minute ago"),
        (timedelta(hours=5), "5 hours ago"),
        (timedelta(days=1, hours=3), "1 day ago"),
        (timedelta(days=65), "2 months ago"),
        (timedelta(days=800), "2 years ago"),
    ],
)
def test_ago(delta: timedelta, expected: str) -> None:
    now = datetime(2026, 10, 9, tzinfo=UTC)
    assert ago(now - delta, now) == expected


def test_time_tag_is_utc() -> None:
    moment = datetime(2026, 10, 9, 19, 59, tzinfo=timezone(timedelta(hours=1)))
    assert time_tag(moment) == (
        '<time datetime="2026-10-09T18:59:00+00:00">2026-10-09 18:59 UTC</time>'
    )


def test_render_markdown_escapes_html() -> None:
    html = render_markdown(
        "# Title\n\n<script>alert(1)</script> and **bold**\n\n```\n<b>code</b>\n```"
    )
    assert "<h1>Title</h1>" in html
    assert "<strong>bold</strong>" in html
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "&lt;b&gt;code&lt;/b&gt;" in html


def test_render_markdown_keeps_underscores_in_words() -> None:
    html = render_markdown("https://example.com/exported_filtered_pairs and _emphasis_")
    assert "exported_filtered_pairs" in html
    assert "<em>emphasis</em>" in html


def test_render_markdown_wraps_tables() -> None:
    # Each table in a wrapper that scrolls sideways; a typed `<table>` stays escaped text.
    html = render_markdown("| a | b |\n|---|---|\n| 1 | 2 |\n\n<table> and `<table>`")
    assert html.startswith('<div class="table-scroll"><table>')
    assert "</table></div>" in html
    assert html.count("<table>") == 1 and html.count("&lt;table&gt;") == 2


# Note pages.


@pytest.fixture
def browser(database: None, api_tokens: dict[str, str]) -> TestClient:
    return TestClient(app, cookies={COOKIE_NAME: api_tokens["rw"]}, follow_redirects=False)


def _create(content: str) -> notes.NoteData:
    with db.session() as session:
        return notes.create_note(session, content)


def test_index(browser: TestClient) -> None:
    response = browser.get("/")
    assert response.status_code == 200
    assert '<input id="search" type="search"' in response.text
    assert 'hx-get="/notes"' in response.text
    assert "/static/app.css" in response.text
    # The top bar: "New note" and "Log out", without the token's name.
    header = response.text.split("</header>")[0]
    assert 'hx-get="/notes/new"' in header and "Log out" in header
    assert ">me<" not in header
    assert response.text.count('hx-get="/notes/new"') == 1


def test_note_list(browser: TestClient) -> None:
    first = _create("First note")
    second = _create("Second note")
    gone = _create("Deleted note")
    with db.session() as session:
        notes.delete_note(session, gone.id)
    html = browser.get("/notes").text
    assert html.index(f'/notes/{second.id}"') < html.index(f'/notes/{first.id}"')
    assert "Deleted note" not in html
    # Rows: title, ID and a live relative time, a preview; no tag badges.
    assert f'<span class="font-mono">#{first.id}</span>' in html
    assert "data-ago>just now</time>" in html


def test_note_list_sorts_by_last_update(browser: TestClient) -> None:
    older = _create("Older note")
    _create("Newer note")
    with db.session() as session:
        notes.update_note(session, older.id, "Older note, edited")
    html = browser.get("/notes").text
    assert html.index("Older note, edited") < html.index("Newer note")


def test_note_list_carries_text_for_search(browser: TestClient) -> None:
    _create('Quotes " and <tags> & ampersands')
    html = browser.get("/notes").text
    assert 'data-text="Quotes &#34; and &lt;tags&gt; &amp; ampersands"' in html
    assert '<li class="no-matches px-4 py-3 text-sm opacity-60" hidden>' in html


def test_tags_in_list_and_note(browser: TestClient) -> None:
    tagged = _create("One\n\nTags: #work, #project/aeris")
    _create("Two\n\nTags: #work")
    html = browser.get("/notes").text
    # No chips or badges: rows carry their tags for filtering by `#tag` in the search box.
    assert "tag-chip" not in html and "badge" not in html
    assert 'data-tags="project/aeris work"' in html
    detail = browser.get(f"/notes/{tagged.id}").text
    assert 'data-tag="project/aeris"' in detail


def test_note_page(browser: TestClient) -> None:
    note = _create("# Heading\n\nBody")
    page = browser.get(f"/n/{note.id}")
    assert page.status_code == 200
    assert 'id="note-list-container"' in page.text
    assert "<h1>Heading</h1>" in page.text
    missing = browser.get("/n/999")
    assert missing.status_code == 404
    assert "Note not found." in missing.text


def test_note_list_links(browser: TestClient) -> None:
    note = _create("Linked")
    html = browser.get("/notes").text
    assert f'href="/n/{note.id}"' in html
    assert f'hx-push-url="/n/{note.id}"' in html
    assert f'data-id="{note.id}"' in html


def test_note_detail(browser: TestClient) -> None:
    note = _create("# Heading\n\n<script>x</script>")
    rendered = browser.get(f"/notes/{note.id}").text
    assert "<h1>Heading</h1>" in rendered
    assert f'<time datetime="{note.created_at.astimezone(UTC).isoformat()}">' in rendered
    assert "&lt;script&gt;" in rendered
    raw = browser.get(f"/notes/{note.id}?mode=raw").text
    assert "# Heading" in raw
    missing = browser.get("/notes/999")
    assert missing.status_code == 404
    assert "Note not found." in missing.text and "text-error" in missing.text


def test_note_detail_bar(browser: TestClient) -> None:
    note = _create("# Heading\nTags: #work\n\nBody")
    html = browser.get(f"/notes/{note.id}").text
    # The bar: ID, dates and actions, outside the scrolling body; tags come after it, in the body.
    bar = html.split("</header>")[0]
    assert '<header class="pane-bar">' in bar
    assert '<div class="note-body flex-1 overflow-y-auto">' in html.split("</header>")[1]
    assert f'<span class="font-mono">#{note.id}</span>' in bar
    assert "Rendered" in bar and "Edit" in bar and "Delete" in bar
    # Phones only (`md:hidden`): back to the list, which the note covers.
    assert 'aria-label="Back to the list"' in bar and 'hx-push-url="/"' in bar
    assert 'data-tag="work"' not in bar
    assert 'data-tag="work"' in html.split("</header>")[1]
    # Raw mode: the text alone, like the editor; no tag badges (the `Tags:` line is in the text).
    raw = browser.get(f"/notes/{note.id}?mode=raw").text
    assert "# Heading\nTags: #work\n\nBody</pre>" in raw
    assert 'data-tag="work"' not in raw and "bg-base-200" not in raw


def test_forms(browser: TestClient) -> None:
    new = browser.get("/notes/new").text
    assert new.startswith('<form class="h-full flex flex-col"\n      hx-post="/notes"')
    assert "expected_updated_at" not in new
    # The bar, inside the form: Save submits it; Cancel on a new note re-requests the page.
    bar = new.split("</header>")[0]
    assert '<button type="submit" class="btn btn-primary btn-sm">Save</button>' in bar
    assert 'hx-get=""\n            hx-select="#main-panel > *"' in bar
    note = _create("Editable")
    edit = browser.get(f"/notes/{note.id}/edit").text
    assert f'hx-put="/notes/{note.id}"' in edit
    assert f'value="{note.updated_at.isoformat()}"' in edit
    assert ">Editable</textarea>" in edit
    assert f'hx-get="/notes/{note.id}"' in edit.split("</header>")[0]  # Cancel.
    assert browser.get("/notes/999/edit").status_code == 404


def test_create_note(browser: TestClient) -> None:
    response = browser.post("/notes", data={"content": "# Fresh"})
    assert response.status_code == 200
    assert response.headers["hx-trigger"] == "noteCreated"
    assert response.headers["hx-push-url"].startswith("/n/")
    assert "<h1>Fresh</h1>" in response.text
    empty = browser.post("/notes", data={"content": "  "})
    assert "Note content cannot be empty." in empty.text
    assert "hx-trigger" not in empty.headers


def test_update_note(browser: TestClient) -> None:
    note = _create("v1")
    data = {"content": "v2", "expected_updated_at": note.updated_at.isoformat()}
    response = browser.put(f"/notes/{note.id}", data=data)
    assert response.headers["hx-trigger"] == "noteUpdated"
    assert "v2" in response.text


def test_update_note_conflict(browser: TestClient) -> None:
    note = _create("v1")
    with db.session() as session:
        newer = notes.update_note(session, note.id, "changed elsewhere")
    data = {"content": "my edit", "expected_updated_at": note.updated_at.isoformat()}
    response = browser.put(f"/notes/{note.id}", data=data)
    assert CONFLICT_MESSAGE in response.text
    assert ">my edit</textarea>" in response.text
    assert f'value="{newer.updated_at.isoformat()}"' in response.text
    assert "hx-trigger" not in response.headers
    # Saving again with the refreshed timestamp overwrites on purpose.
    data["expected_updated_at"] = newer.updated_at.isoformat()
    assert browser.put(f"/notes/{note.id}", data=data).headers["hx-trigger"] == "noteUpdated"


def test_delete_note(browser: TestClient) -> None:
    note = _create("Doomed")
    detail = browser.get(f"/notes/{note.id}").text
    assert f'hx-delete="/notes/{note.id}"' in detail
    assert 'hx-confirm="Delete this note?"' in detail

    response = browser.delete(f"/notes/{note.id}")
    assert response.status_code == 200
    assert response.headers["hx-trigger"] == "noteDeleted"
    assert response.headers["hx-push-url"] == "/"
    assert f"Note #{note.id} deleted." in response.text
    assert "Doomed" not in browser.get("/notes").text
    assert browser.get(f"/notes/{note.id}").status_code == 404
    assert browser.delete(f"/notes/{note.id}").status_code == 404


def test_index_refreshes_list_after_delete(browser: TestClient) -> None:
    assert "noteDeleted from:body" in browser.get("/").text


def test_web_writes_require_rw(database: None, api_tokens: dict[str, str]) -> None:
    reader = TestClient(app, cookies={COOKIE_NAME: api_tokens["ro"]})
    assert reader.post("/notes", data={"content": "x"}).status_code == 403
    assert reader.put("/notes/1", data={"content": "x"}).status_code == 403
    assert reader.delete("/notes/1").status_code == 403
