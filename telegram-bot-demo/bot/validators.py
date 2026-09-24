"""Валидация и нормализация пользовательского ввода (чистые функции, без aiogram)."""

from __future__ import annotations

import re

NAME_MIN_LEN = 2
NAME_MAX_LEN = 50
COMMENT_MAX_LEN = 1000

_PHONE_ALLOWED_RE = re.compile(r"^\+?[\d\s().\-]+$")
_NAME_EXTRA_CHARS = frozenset(" -'’.")


def normalize_name(raw: str | None) -> str | None:
    """Возвращает аккуратное имя или ``None``, если ввод не похож на имя.

    Допускаются буквы любого алфавита, пробел, дефис, апостроф и точка.
    Лишние пробелы схлопываются.
    """
    if not raw:
        return None
    name = " ".join(raw.split())
    if not NAME_MIN_LEN <= len(name) <= NAME_MAX_LEN:
        return None
    if not name[0].isalpha():
        return None
    if not all(ch.isalpha() or ch in _NAME_EXTRA_CHARS for ch in name):
        return None
    if sum(ch.isalpha() for ch in name) < NAME_MIN_LEN:
        return None
    return name


def normalize_phone(raw: str | None) -> str | None:
    """Приводит телефон к формату E.164 (``+79001234567``) или возвращает ``None``.

    Понимает ``+7 (900) 123-45-67``, ``8 900 123 45 67``, ``9001234567``, ``(495) 123-45-67``,
    номера из «Поделиться контактом» (``79001234567``) и международные ``+44 20 7946 0958``.
    """
    if not raw:
        return None
    value = raw.strip()
    if not value or not _PHONE_ALLOWED_RE.fullmatch(value):
        return None

    has_plus = value.startswith("+")
    digits = re.sub(r"\D", "", value)

    if not has_plus:
        if len(digits) == 11 and digits[0] == "8":
            digits = "7" + digits[1:]  # 8 900 ... -> +7 900 ...
        elif len(digits) == 10 and digits[0] in "34789":
            # 10 цифр без кода страны: мобильный (900…) или городской (495…, 812…) номер РФ/КЗ
            digits = "7" + digits

    if not 10 <= len(digits) <= 15:  # E.164: максимум 15 цифр
        return None
    if digits[0] == "0":
        return None
    if digits[0] == "7" and len(digits) != 11:  # РФ/КЗ: всегда 11 цифр
        return None
    return "+" + digits


def format_phone(phone: str) -> str:
    """Человекочитаемый вид: ``+79001234567`` -> ``+7 (900) 123-45-67``."""
    if len(phone) == 12 and phone.startswith("+7") and phone[1:].isdigit():
        d = phone[2:]
        return f"+7 ({d[:3]}) {d[3:6]}-{d[6:8]}-{d[8:]}"
    return phone


def normalize_comment(raw: str | None) -> str:
    """Обрезает пробелы по краям; длину проверяет :func:`comment_is_valid`."""
    return (raw or "").strip()


def comment_is_valid(comment: str) -> bool:
    return len(comment) <= COMMENT_MAX_LEN
