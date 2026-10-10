"""Screenshot gallery: fixed views of the running UI sandbox, for before/after comparisons.

    uv run dev/screenshots.py [LABEL]
    uv run dev/screenshots.py --compare LABEL LABEL...

Needs the sandbox (`uv run dev/sandbox.py`) running. Writes `dev/screenshots/LABEL/VIEW-WIDTH.png`
for every view and size, plus an `index.html` showing them all. LABEL defaults to the date and
time. `--compare` writes `dev/screenshots/compare.html`: existing galleries side by side.
Read-only: it opens forms but never saves.
"""

import argparse
import html
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import httpx
from playwright.sync_api import Page, sync_playwright
from sandbox import PORT

BASE = f"http://localhost:{PORT}"
OUT = Path(__file__).resolve().parent / "screenshots"
SIZES = {1440: 900, 1024: 700}  # Width: height. A desktop window, and a narrow one.


def settle(page: Page) -> None:
    """Wait until the network is quiet and htmx has finished swapping."""
    page.wait_for_load_state("networkidle")
    page.wait_for_function(
        "() => !document.querySelector('.htmx-request, .htmx-swapping, .htmx-settling')"
    )


def go(path: str) -> Callable[[Page], None]:
    def view(page: Page) -> None:
        page.goto(BASE + path)

    return view


def edit(page: Page) -> None:
    page.goto(f"{BASE}/n/2")
    settle(page)
    page.get_by_role("button", name="Edit").click()


def new(page: Page) -> None:
    page.goto(f"{BASE}/")
    settle(page)
    page.get_by_role("button", name="New note").click()


def search(text: str, *, enter: bool = False) -> Callable[[Page], None]:
    def view(page: Page) -> None:
        page.goto(f"{BASE}/")
        settle(page)
        page.locator("#search").fill(text)
        if enter:
            page.locator("#search").press("Enter")
            page.wait_for_selector("#ranked-notes li, #ranked-notes .text-error")

    return view


# Logged in, except `login`. Note IDs follow the fixtures' order: 1 is the weekly sync, 2 the long
# Ray how-to.
VIEWS: dict[str, Callable[[Page], None]] = {
    "home": go("/"),
    "note": go("/n/1"),
    "note-long": go("/n/2"),
    "edit": edit,
    "new": new,
    "filter": search("kubernetes"),
    "no-match": search("zebra"),
    "ranked": search("cluster", enter=True),
    "login": go("/login"),
    "styleguide": go("/dev/styleguide"),
}
FULL_PAGE = {"styleguide"}  # Long pages that scroll as a whole: capture all of it.


def write_index(folder: Path, shots: list[Path]) -> None:
    figures = "\n".join(
        f'<figure><img src="{shot.name}" alt=""><figcaption>{html.escape(shot.stem)}'
        "</figcaption></figure>"
        for shot in shots
    )
    folder.joinpath("index.html").write_text(
        f"""<!doctype html>
<meta charset="utf-8">
<title>aeris screenshots: {html.escape(folder.name)}</title>
<style>
  body {{ font-family: system-ui, sans-serif; margin: 24px; background: #f4f4f5; }}
  figure {{ margin: 0 0 32px; }}
  img {{ max-width: 100%; border: 1px solid #d4d4d8; background: white; }}
  figcaption {{ font-size: 14px; color: #52525b; margin-top: 4px; }}
</style>
<h1>{html.escape(folder.name)}</h1>
{figures}
"""
    )


def write_comparison(labels: list[str]) -> Path:
    """One row per screenshot, one column per gallery."""
    names = sorted(path.name for path in (OUT / labels[0]).glob("*.png"))
    head = "".join(f"<th>{html.escape(label)}</th>" for label in labels)
    rows = "\n".join(
        f"<tr><td colspan={len(labels)}>{html.escape(name)}</td></tr><tr>"
        + "".join(f'<td><img src="{label}/{name}" alt=""></td>' for label in labels)
        + "</tr>"
        for name in names
    )
    page = OUT / "compare.html"
    page.write_text(
        f"""<!doctype html>
<meta charset="utf-8">
<title>aeris screenshots: {html.escape(" vs ".join(labels))}</title>
<style>
  body {{ font-family: system-ui, sans-serif; margin: 16px; background: #f4f4f5; }}
  table {{ border-spacing: 12px 4px; width: 100%; table-layout: fixed; }}
  th {{ text-align: left; position: sticky; top: 0; background: #f4f4f5; padding: 8px 0; }}
  td {{ vertical-align: top; font-size: 13px; color: #52525b; }}
  img {{ width: 100%; border: 1px solid #d4d4d8; background: white; }}
</style>
<table><tr>{head}</tr>
{rows}
</table>
"""
    )
    return page


def main() -> None:
    parser = argparse.ArgumentParser(description="Screenshot the running UI sandbox.")
    parser.add_argument("label", nargs="?", default=datetime.now().strftime("%Y-%m-%d-%H%M%S"))
    parser.add_argument("--compare", nargs="+", metavar="LABEL", help="Compare galleries.")
    args = parser.parse_args()
    if args.compare:
        print(f"Wrote {write_comparison(args.compare)}")
        return
    label = args.label
    try:
        httpx.get(f"{BASE}/healthz", timeout=2).raise_for_status()
    except httpx.HTTPError:
        raise SystemExit(f"No sandbox at {BASE}: start it with `uv run dev/sandbox.py`.") from None

    folder = OUT / label
    folder.mkdir(parents=True, exist_ok=True)
    shots: list[Path] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        for width, height in SIZES.items():
            logged_in = browser.new_context(viewport={"width": width, "height": height})
            logged_in.new_page().goto(f"{BASE}/dev/login")
            logged_out = browser.new_context(viewport={"width": width, "height": height})
            for name, show in VIEWS.items():
                page = (logged_out if name == "login" else logged_in).new_page()
                show(page)
                settle(page)
                page.evaluate("document.fonts.ready")
                shot = folder / f"{name}-{width}.png"
                page.screenshot(path=shot, full_page=name in FULL_PAGE)
                page.close()
                shots.append(shot)
        browser.close()
    write_index(folder, sorted(shots))
    print(f"{len(shots)} screenshots in {folder}/ (index.html shows them all)")


if __name__ == "__main__":
    main()
