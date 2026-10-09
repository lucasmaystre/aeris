import pytest

from aeris_server.parsing import (
    SNIPPET_LENGTH,
    TITLE_MAX_LENGTH,
    extract_tags,
    normalize,
    snippet,
    title,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("", ""),
        ("Distributed Systems", "distributed systems"),
        # Accents are stripped, whether precomposed or already decomposed.
        ("Éte", "ete"),
        ("naïve café", "naive cafe"),
        ("Café", "cafe"),
        ("Άλφα Ωμέγα", "αλφα ωμεγα"),
        ("İstanbul", "istanbul"),
        # Compatibility characters become their plain equivalents.
        ("ﬁle", "file"),
        ("x²", "x2"),
        ("ＡＢＣ", "abc"),
        ("ℌello", "hello"),
        # Whitespace runs, including line breaks and non-breaking spaces, become one space.
        ("distributed\n  systems", "distributed systems"),
        ("a b\tc\r\nd", "a b c d"),
        (" leading and trailing ", " leading and trailing "),
        # Known limitation: letters that aren't accented forms in Unicode stay as they are.
        ("Ørsted", "ørsted"),
        ("Æsir", "æsir"),
        ("Straße", "straße"),
    ],
)
def test_normalize(text: str, expected: str) -> None:
    assert normalize(text) == expected


def test_normalize_is_idempotent() -> None:
    text = "Ünïcödé  ﬁle\nİstanbul"
    assert normalize(normalize(text)) == normalize(text)


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ("", []),
        ("No tags here.", []),
        ("Title\n\nTags: #aeris, #notes", ["aeris", "notes"]),
        ("Tags: #b #a\n", ["a", "b"]),
        ("tags: #x", ["x"]),
        ("  TAGS:#x;#y", ["x", "y"]),
        ("Tags:", []),
        # Several lines, anywhere in the note, are merged.
        ("Tags: #a\nbody\nTags: #b", ["a", "b"]),
        # Tags elsewhere in the note are ignored.
        ("Talked about #aeris today.\nTags: #work", ["work"]),
        ("My tags: #x", []),
        ("Tagsx: #x", []),
        # Tag syntax.
        (
            "Tags: #project/aeris, #to-do, #snake_case, #v2",
            ["project/aeris", "snake_case", "to-do", "v2"],
        ),
        ("Tags: #café, #日本", ["café", "日本"]),
        ("Tags: #12, #1abc, #, #_x, plain", []),
        # Lowercased and deduplicated.
        ("Tags: #Aeris, #aeris\nTags: #AERIS", ["aeris"]),
    ],
)
def test_extract_tags(content: str, expected: list[str]) -> None:
    assert extract_tags(content) == expected


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ("", ""),
        ("Hello world", "Hello world"),
        ("\n\n  Hello   world  \nsecond line", "Hello world"),
        # Tag lines and lines without text are skipped.
        ("Tags: #a, #b\n\nActual title", "Actual title"),
        ("Tags: #a", ""),
        ("#\n---\n* * *\n>\nReal", "Real"),
        # Block markers.
        ("# Heading", "Heading"),
        ("### Deep heading ###", "Deep heading ###"),
        ("#hashtag start", "#hashtag start"),
        ("> Quoted", "Quoted"),
        ("- Bullet", "Bullet"),
        ("* Bullet", "Bullet"),
        ("+ Bullet", "Bullet"),
        ("12. Numbered", "Numbered"),
        ("- [ ] Task", "Task"),
        ("> - [x] Done task", "Done task"),
        # Inline markdown.
        ("**Bold** and __bold__", "Bold and bold"),
        ("*Em* and _em_", "Em and em"),
        ("~~Gone~~ here", "Gone here"),
        ("Run `uv sync` now", "Run uv sync now"),
        ("``a`b``", "a`b"),
        ("See [the docs](https://example.com)", "See the docs"),
        ("![A diagram](img.png)", "A diagram"),
        ("<https://example.com>", "https://example.com"),
        ("snake_case_name and 5 * 3", "snake_case_name and 5 * 3"),
        ("\\*not emphasis\\* and \\# literal", "*not emphasis* and # literal"),
        ("\\# Not a heading", "# Not a heading"),
    ],
)
def test_title(content: str, expected: str) -> None:
    assert title(content) == expected


def test_title_truncates_at_word_boundary() -> None:
    content = "word " * 30
    result = title(content)
    assert result.endswith("word…")
    assert len(result) <= TITLE_MAX_LENGTH


def test_title_truncates_long_word() -> None:
    result = title("x" * 200)
    assert result == "x" * (TITLE_MAX_LENGTH - 1) + "…"


def test_title_keeps_exact_length() -> None:
    content = "y" * TITLE_MAX_LENGTH
    assert title(content) == content


def test_snippet_short_content_is_whole() -> None:
    assert snippet("A short\n\nnote.", "short") == "A short note."


def test_snippet_cuts_around_match() -> None:
    content = (
        " ".join(f"w{i}" for i in range(200)) + " needle " + " ".join(f"v{i}" for i in range(200))
    )
    result = snippet(content, "needle")
    assert result.startswith("…w")
    assert result.endswith("…")
    assert " needle " in result
    assert len(result) <= SNIPPET_LENGTH + 2
    # Cut at word boundaries: no partial words at either end.
    assert result.split()[0].removeprefix("…") in content.split()
    assert result.split()[-1].removesuffix("…") in content.split()


def test_snippet_match_at_start() -> None:
    content = "needle " + "word " * 100
    result = snippet(content, "needle")
    assert result.startswith("needle word")
    assert result.endswith("…")


def test_snippet_shows_original_text() -> None:
    content = "x " * 100 + "Un Été très chaud" + " y" * 100
    assert "Un Été très" in snippet(content, "ete TRES")


def test_snippet_matches_across_line_break() -> None:
    content = "x " * 100 + "distributed\n   systems" + " y" * 100
    assert "distributed systems" in snippet(content, "distributed systems")


def test_snippet_maps_positions_after_expanding_characters() -> None:
    # Each `ﬁ` becomes two characters when normalized; the window must still find the original.
    content = "ﬁ" * 300 + " target " + "x" * 300
    assert "target" in snippet(content, "target")


def test_snippet_without_match_shows_start() -> None:
    content = "Beginning " + "word " * 100
    result = snippet(content, "absent")
    assert result.startswith("Beginning word")
    assert result.endswith("…")
