"""Optional Google Sheets export (gspread).

Not needed for the demo to run: gspread is imported lazily and is only
required when `--gsheet` is used. Setup is described in README.md
(service account JSON + share the spreadsheet with its e-mail).
"""

from __future__ import annotations

from pathlib import Path

from bookscraper.exporters.tabular import COLUMNS, row_values
from bookscraper.models import Book


class GSheetsUnavailable(RuntimeError):
    pass


def write_gsheet(
    books: list[Book],
    spreadsheet: str,
    *,
    credentials_file: str | Path,
    worksheet: str = "Books",
) -> str:
    """Write books to `worksheet` of `spreadsheet` (key, URL or title).
    Returns the spreadsheet URL."""
    try:
        import gspread  # type: ignore[import-not-found]
        from google.auth.exceptions import GoogleAuthError  # installed together with gspread
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise GSheetsUnavailable(
            "Google Sheets export needs gspread: pip install -r requirements-gsheets.txt"
        ) from exc

    creds = Path(credentials_file).expanduser()
    if not creds.is_file():
        raise GSheetsUnavailable(f"service-account file not found: {creds}")

    rows = [[c.header for c in COLUMNS]]
    rows += [["" if v is None else v for v in row_values(b)] for b in books]

    try:
        client = gspread.service_account(filename=str(creds))
        if spreadsheet.startswith("http"):
            sh = client.open_by_url(spreadsheet)
        else:
            try:
                sh = client.open_by_key(spreadsheet)
            except gspread.SpreadsheetNotFound:
                sh = client.open(spreadsheet)

        try:
            ws = sh.worksheet(worksheet)
            ws.clear()
        except gspread.WorksheetNotFound:
            ws = sh.add_worksheet(title=worksheet, rows=len(rows), cols=len(COLUMNS))
        # the grid must fit the data (an existing sheet may be smaller than this run)
        ws.resize(rows=max(len(rows), 2), cols=len(COLUMNS))

        ws.update(rows, "A1", value_input_option="RAW")
        ws.freeze(rows=1, cols=1)
        ws.format("1:1", {"textFormat": {"bold": True}})
        ws.set_basic_filter()
    except gspread.SpreadsheetNotFound as exc:
        raise GSheetsUnavailable(
            f"spreadsheet {spreadsheet!r} not found — check the ID/URL and share it "
            "with the service-account e-mail (Editor)"
        ) from exc
    except (gspread.exceptions.GSpreadException, GoogleAuthError, ValueError, OSError) as exc:
        raise GSheetsUnavailable(f"Google Sheets export failed: {type(exc).__name__}: {exc}") from exc
    return sh.url
