import pytest

from aeris_server.parsing import normalize


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
