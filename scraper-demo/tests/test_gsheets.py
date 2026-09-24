"""Google Sheets exporter against a fake `gspread` module (no network, no credentials)."""

from __future__ import annotations

import sys
import types

import pytest

from bookscraper.exporters.gsheets import GSheetsUnavailable, write_gsheet
from bookscraper.models import Book


def make_book(i: int) -> Book:
    return Book(title=f"Book {i}", price=10.0 + i, currency="GBP", availability=i, in_stock=True,
                rating=3, upc=f"upc{i}", category="Poetry", description="", image_url="",
                product_url=f"https://books.toscrape.com/catalogue/book_{i}/index.html")


class _Err(Exception):
    pass


def fake_gspread(*, sheet_exists: bool, found: bool = True):
    calls: list[tuple] = []

    class Worksheet:
        def clear(self):
            calls.append(("clear",))

        def resize(self, rows, cols):
            calls.append(("resize", rows, cols))

        def update(self, values, range_name, value_input_option=None):
            calls.append(("update", len(values), range_name))

        def freeze(self, rows, cols):
            calls.append(("freeze", rows, cols))

        def format(self, rng, fmt):
            calls.append(("format", rng))

        def set_basic_filter(self):
            calls.append(("filter",))

    class Spreadsheet:
        url = "https://docs.google.com/spreadsheets/d/FAKE"

        def worksheet(self, name):
            if not sheet_exists:
                raise mod.WorksheetNotFound(name)
            return Worksheet()

        def add_worksheet(self, title, rows, cols):
            calls.append(("add", title, rows, cols))
            return Worksheet()

    class Client:
        def open_by_key(self, key):
            if not found:
                raise mod.SpreadsheetNotFound(key)
            return Spreadsheet()

        open_by_url = open_by_key

        def open(self, title):
            raise mod.SpreadsheetNotFound(title)

    mod = types.ModuleType("gspread")
    mod.exceptions = types.SimpleNamespace(GSpreadException=_Err)
    mod.SpreadsheetNotFound = type("SpreadsheetNotFound", (_Err,), {})
    mod.WorksheetNotFound = type("WorksheetNotFound", (_Err,), {})
    mod.service_account = lambda filename: Client()

    auth = types.ModuleType("google.auth.exceptions")
    auth.GoogleAuthError = type("GoogleAuthError", (Exception,), {})
    return mod, auth, calls


@pytest.fixture
def creds(tmp_path):
    path = tmp_path / "service_account.json"
    path.write_text("{}")
    return path


def install(monkeypatch, mod, auth):
    monkeypatch.setitem(sys.modules, "gspread", mod)
    monkeypatch.setitem(sys.modules, "google", types.ModuleType("google"))
    monkeypatch.setitem(sys.modules, "google.auth", types.ModuleType("google.auth"))
    monkeypatch.setitem(sys.modules, "google.auth.exceptions", auth)


def test_existing_sheet_is_cleared_and_resized_to_fit(monkeypatch, creds):
    mod, auth, calls = fake_gspread(sheet_exists=True)
    install(monkeypatch, mod, auth)
    books = [make_book(i) for i in range(1, 6)]
    url = write_gsheet(books, "KEY", credentials_file=creds)
    assert url.endswith("/FAKE")
    names = [c[0] for c in calls]
    assert names.index("clear") < names.index("resize") < names.index("update")
    assert ("resize", 6, 11) in calls and ("update", 6, "A1") in calls
    assert ("freeze", 1, 1) in calls and ("filter",) in calls


def test_missing_sheet_is_created(monkeypatch, creds):
    mod, auth, calls = fake_gspread(sheet_exists=False)
    install(monkeypatch, mod, auth)
    write_gsheet([make_book(1)], "KEY", credentials_file=creds)
    assert ("add", "Books", 2, 11) in calls


def test_spreadsheet_not_found_gives_clear_error(monkeypatch, creds):
    mod, auth, _ = fake_gspread(sheet_exists=True, found=False)
    install(monkeypatch, mod, auth)
    with pytest.raises(GSheetsUnavailable, match="share it"):
        write_gsheet([make_book(1)], "KEY", credentials_file=creds)


def test_missing_credentials_file(monkeypatch, tmp_path):
    mod, auth, _ = fake_gspread(sheet_exists=True)
    install(monkeypatch, mod, auth)
    with pytest.raises(GSheetsUnavailable, match="service-account file not found"):
        write_gsheet([make_book(1)], "KEY", credentials_file=tmp_path / "nope.json")
