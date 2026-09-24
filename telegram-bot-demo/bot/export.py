"""Выгрузка заявок в CSV, который корректно открывается в Excel и Google Таблицах."""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable
from datetime import tzinfo

from bot.db import Lead
from bot.formatting import format_dt, service_title, status_title

CSV_HEADERS = (
    "№",
    "Дата",
    "Статус",
    "Имя",
    "Телефон",
    "Услуга",
    "Комментарий",
    "Telegram username",
    "Telegram имя",
    "Telegram ID",
)

# Символы, с которых Excel/LibreOffice начинают формулу (CSV/formula injection).
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def sanitize_cell(value: str) -> str:
    """Экранирует ячейку, чтобы пользовательский текст не выполнился как формула."""
    if value and value.startswith(_FORMULA_PREFIXES):
        return "'" + value
    return value


def leads_to_csv(leads: Iterable[Lead], tz: tzinfo, *, delimiter: str = ";") -> bytes:
    """Возвращает CSV в UTF-8 с BOM.

    Разделитель по умолчанию «;» — так файл сразу раскладывается по столбцам
    в Excel с русской локалью. BOM нужен, чтобы Excel не ломал кириллицу.
    """
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, delimiter=delimiter, lineterminator="\r\n")
    writer.writerow(CSV_HEADERS)
    for lead in leads:
        writer.writerow(
            (
                lead.id,
                format_dt(lead.created_at, tz),
                status_title(lead.status),
                sanitize_cell(lead.name),
                lead.phone,  # уже нормализован валидатором: только «+» и цифры
                service_title(lead.service),
                sanitize_cell(lead.comment),
                lead.username or "",  # без «@»: Excel считает «@...» началом формулы
                sanitize_cell(lead.tg_full_name),
                lead.user_id,
            )
        )
    return buffer.getvalue().encode("utf-8-sig")
