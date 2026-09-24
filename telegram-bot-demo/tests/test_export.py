import csv
import io
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from bot.db import Lead
from bot.export import CSV_HEADERS, leads_to_csv, sanitize_cell

MSK = ZoneInfo("Europe/Moscow")


def make_lead(lead_id: int = 1, **overrides) -> Lead:
    data = {
        "id": lead_id,
        "user_id": 555,
        "username": "anna_demo",
        "tg_full_name": "Анна Смирнова",
        "name": "Анна",
        "phone": "+79001234567",
        "service": "landing",
        "comment": "Нужен сайт; с «кавычками», запятыми и\nпереносом строки",
        "status": "new",
        "created_at": datetime(2026, 9, 24, 9, 30, tzinfo=UTC),
    }
    data.update(overrides)
    return Lead(**data)


def parse(payload: bytes, delimiter: str = ";") -> list[list[str]]:
    assert payload.startswith(b"\xef\xbb\xbf"), "нужен BOM, иначе Excel ломает кириллицу"
    return list(csv.reader(io.StringIO(payload.decode("utf-8-sig"), newline=""), delimiter=delimiter))


def test_csv_structure_and_values() -> None:
    rows = parse(leads_to_csv([make_lead(1), make_lead(2, username=None, comment="", status="done")], MSK))
    assert rows[0] == list(CSV_HEADERS)
    assert len(rows) == 3

    first = dict(zip(CSV_HEADERS, rows[1], strict=True))
    assert first["№"] == "1"
    assert first["Дата"] == "24.09.2026 12:30"  # UTC -> МСК
    assert first["Статус"] == "🆕 Новая"
    assert first["Телефон"] == "+79001234567"
    assert first["Услуга"] == "Лендинг"
    assert first["Комментарий"] == "Нужен сайт; с «кавычками», запятыми и\nпереносом строки"
    assert first["Telegram username"] == "anna_demo"
    assert first["Telegram ID"] == "555"

    second = dict(zip(CSV_HEADERS, rows[2], strict=True))
    assert second["Telegram username"] == ""
    assert second["Статус"] == "✅ Закрыта"


def test_csv_empty_has_only_header() -> None:
    assert parse(leads_to_csv([], MSK)) == [list(CSV_HEADERS)]


def test_csv_custom_delimiter() -> None:
    rows = parse(leads_to_csv([make_lead()], MSK, delimiter=","), delimiter=",")
    assert rows[1][0] == "1"


def test_formula_injection_is_neutralized() -> None:
    lead = make_lead(comment='=HYPERLINK("http://evil.example","click")', tg_full_name="@SUM(A1)")
    rows = parse(leads_to_csv([lead], MSK))
    row = dict(zip(CSV_HEADERS, rows[1], strict=True))
    assert row["Комментарий"].startswith("'=")
    assert row["Telegram имя"].startswith("'@")


def test_sanitize_cell() -> None:
    assert sanitize_cell("=1+1") == "'=1+1"
    assert sanitize_cell("-5") == "'-5"
    assert sanitize_cell("обычный текст") == "обычный текст"
    assert sanitize_cell("") == ""
