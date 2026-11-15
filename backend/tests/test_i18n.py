"""The translated UI strings: every language must have every string."""

import json
import re
from pathlib import Path

STRINGS = json.loads(
    (Path(__file__).resolve().parents[2] / "frontend" / "src" / "i18n" / "strings.json").read_text())
LANGUAGES = {"en", "es", "hi", "te", "ta", "pt", "zh", "ar", "am"}
# The judge panel (?debug=1) is always English on purpose, so these keys are English-only.
ENGLISH_ONLY = {"judge_panel", "jump_to_screen"}


def test_all_nine_languages_are_present():
    assert set(STRINGS) == LANGUAGES


def test_every_language_has_exactly_the_english_keys():
    shared = set(STRINGS["en"]) - ENGLISH_ONLY
    assert ENGLISH_ONLY <= set(STRINGS["en"])
    for code, table in STRINGS.items():
        expected = set(STRINGS["en"]) if code == "en" else shared
        assert set(table) == expected, (code, sorted(expected ^ set(table))[:5])


def test_no_empty_strings():
    for code, table in STRINGS.items():
        for key, value in table.items():
            assert value.strip(), (code, key)


def test_placeholders_match_the_english_text():
    """{amount}, {merchant} and friends must survive translation."""
    for key, english in STRINGS["en"].items():
        wanted = set(re.findall(r"\{(\w+)\}", english))
        for code, table in STRINGS.items():
            if key in table:
                assert set(re.findall(r"\{(\w+)\}", table[key])) == wanted, (code, key)


def test_english_never_calls_a_letter_safe_legitimate_or_verified():
    for key, value in STRINGS["en"].items():
        assert not re.search(r"\b(safe|legitimate|verified|injection-proof)\b", value, re.I), key


def test_digits_in_translations_are_western():
    """The app always shows 0-9, even in Arabic, Hindi, Tamil and Telugu."""
    import unicodedata
    for code, table in STRINGS.items():
        for key, value in table.items():
            for char in value:
                if unicodedata.category(char) == "Nd":
                    assert char in "0123456789", (code, key, char)
