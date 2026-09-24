from datetime import date

import pytest

from xldash.csvio import canonical_spelling, map_headers, parse_date, parse_number, sniff_rows


@pytest.mark.parametrize("text, expected", [
    ("7.5", 7.5), ("7,5", 7.5), (" 1 234,50 ", 1234.5), ("1,234.50", 1234.5),
    ("1.234,50", 1234.5), ("0", 0.0), ("-15", -15.0), ("12 000", 12000.0),
])
def test_parse_number(text, expected):
    assert parse_number(text) == pytest.approx(expected)


@pytest.mark.parametrize("text", ["", "  ", "abc"])
def test_parse_number_rejects_garbage(text):
    with pytest.raises(ValueError):
        parse_number(text)


@pytest.mark.parametrize("text", ["2026-09-03", "03.09.2026", "03/09/2026", "2026/09/03", " 2026-09-03 "])
def test_parse_date_formats(text):
    assert parse_date(text) == date(2026, 9, 3)


@pytest.mark.parametrize("text", ["2026-13-45", "45.13.2026", "yesterday", ""])
def test_parse_date_rejects_invalid(text):
    with pytest.raises(ValueError):
        parse_date(text)


def test_sniff_semicolon_and_comma():
    assert sniff_rows("a;b;c\n1;2,5;3\n")[1] == ["1", "2,5", "3"]
    assert sniff_rows('a,b,c\n1,"2,5",3\n')[1] == ["1", "2,5", "3"]


def test_map_headers_aliases_and_case():
    aliases = {"run_hours": ("часы работы",), "halt_minutes": ("простой мин",)}
    cols = map_headers(["Дата", "Часы работы", "Простой, мин"], aliases)
    assert cols == {"run_hours": 1, "halt_minutes": 2}
    assert map_headers(["RUN_HOURS"], aliases) == {"run_hours": 0}


def test_canonical_spelling_prefers_most_common():
    mapping = canonical_spelling(["Day", "Day", "day", "DAY", "Night"])
    assert mapping["day"] == "Day" and mapping["DAY"] == "Day" and mapping["Night"] == "Night"
