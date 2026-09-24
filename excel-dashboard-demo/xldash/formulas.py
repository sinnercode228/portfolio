"""Small helpers for building Excel formula text."""

from __future__ import annotations


def quote_sheet(sheet: str) -> str:
    """'Sheet name' for cross-sheet references (always quoted - safe for spaces and Cyrillic)."""
    return "'" + sheet.replace("'", "''") + "'"


def date_text(ref: str, lang: str) -> str:
    """Formula that renders a date as text without TEXT(): TEXT's format codes depend on the
    Excel UI language ("yyyy" is "ГГГГ" in Russian Excel), DAY/MONTH/YEAR do not."""
    dd = f'RIGHT("0"&DAY({ref}),2)'
    mm = f'RIGHT("0"&MONTH({ref}),2)'
    if lang == "ru":
        return f'{dd}&"."&{mm}&"."&YEAR({ref})'
    return f'YEAR({ref})&"-"&{mm}&"-"&{dd}'
