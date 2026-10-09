import pytest

from aeris_server.parsing import extract_tags, normalize


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
