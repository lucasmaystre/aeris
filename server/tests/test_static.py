import pytest
from fastapi.testclient import TestClient

from aeris_server.app import STATIC_DIR, app

client = TestClient(app)


@pytest.mark.parametrize(
    ("path", "content_type"),
    [
        ("/static/app.css", "text/css"),
        ("/static/htmx.min.js", "text/javascript"),
        ("/static/app.js", "text/javascript"),
    ],
)
def test_static_file(path: str, content_type: str) -> None:
    response = client.get(path)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith(content_type)


def test_built_css_has_theme_and_template_classes() -> None:
    # Guards against committing a stale or broken build (rebuild with scripts/css.sh).
    css = (STATIC_DIR / "app.css").read_text()
    needles = [
        "[data-theme=aeris]",
        "--color-primary:#4f46e5",
        "font-family:Inter",
        "--tw-prose-pre-bg:var(--color-base-200)",  # Light code blocks in notes.
        ".btn-primary",
        ":not(:has(.pane-bar)){display:none}",  # Phones: one pane at a time.
        "@media (pointer:coarse){.note-source{font-size:var(--text-base)",  # No iOS zoom.
    ]
    for needle in needles:
        assert needle in css


def test_pages_load_nothing_from_cdns() -> None:
    html = client.get("/login").text
    assert '<link rel="stylesheet" href="/static/app.css">' in html
    assert '<script src="/static/htmx.min.js"></script>' in html
    assert '<script src="/static/app.js"></script>' in html
    assert "cdn." not in html and "https://" not in html
