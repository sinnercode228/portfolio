import pytest

from bot.validators import (
    COMMENT_MAX_LEN,
    comment_is_valid,
    format_phone,
    normalize_comment,
    normalize_name,
    normalize_phone,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Анна", "Анна"),
        ("  иван   петров ", "иван петров"),
        ("Анна-Мария", "Анна-Мария"),
        ("O'Connor", "O'Connor"),
        ("Jean-Luc", "Jean-Luc"),
        ("Ёжик", "Ёжик"),
        ("Олександр", "Олександр"),
    ],
)
def test_normalize_name_valid(raw: str, expected: str) -> None:
    assert normalize_name(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [None, "", "   ", "A", "123", "Анна123", "-Анна", "<b>Иван</b>", "Иван 😀", "a" * 51, "/start", "И."],
)
def test_normalize_name_invalid(raw: str | None) -> None:
    assert normalize_name(raw) is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("+7 900 123-45-67", "+79001234567"),
        ("+7 (900) 123-45-67", "+79001234567"),
        ("8 900 123 45 67", "+79001234567"),
        ("8(900)1234567", "+79001234567"),
        ("9001234567", "+79001234567"),
        ("(495) 123-45-67", "+74951234567"),  # городской номер без кода страны
        ("812 123 45 67", "+78121234567"),
        ("79001234567", "+79001234567"),  # так приходит номер из «Поделиться контактом»
        ("+7.900.123.45.67", "+79001234567"),
        ("+44 20 7946 0958", "+442079460958"),
        ("+1 (415) 555-2671", "+14155552671"),
        ("+380 44 123 4567", "+380441234567"),
    ],
)
def test_normalize_phone_valid(raw: str, expected: str) -> None:
    assert normalize_phone(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        None,
        "",
        "   ",
        "123",
        "+7 900 123",  # слишком короткий для РФ
        "+7 900 123 45 678",  # слишком длинный для РФ
        "+0 123 456 7890",  # код страны не может начинаться с 0
        "телефон 89001234567",
        "8-900-CALL-NOW",
        "+7 900 123 45 67 доб. 5",
        "++79001234567",
        "+1234567890123456",  # больше 15 цифр (E.164)
    ],
)
def test_normalize_phone_invalid(raw: str | None) -> None:
    assert normalize_phone(raw) is None


def test_format_phone() -> None:
    assert format_phone("+79001234567") == "+7 (900) 123-45-67"
    assert format_phone("+442079460958") == "+442079460958"


def test_comment_validation() -> None:
    assert normalize_comment("  нужен лендинг  ") == "нужен лендинг"
    assert normalize_comment(None) == ""
    assert comment_is_valid("x" * COMMENT_MAX_LEN)
    assert not comment_is_valid("x" * (COMMENT_MAX_LEN + 1))
