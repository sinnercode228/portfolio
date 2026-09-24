"""Exporters: list[Book] -> file (xlsx / csv / json) or Google Sheets."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path

from bookscraper.exporters.excel import write_xlsx
from bookscraper.exporters.tabular import COLUMNS, Column, write_csv, write_json
from bookscraper.models import Book

WRITERS: dict[str, Callable[..., Path]] = {
    ".xlsx": write_xlsx,
    ".csv": write_csv,
    ".json": write_json,
}
DEFAULT_FORMATS = (".xlsx", ".csv", ".json")


def resolve_outputs(outs: Iterable[str]) -> list[Path]:
    """`output/books.xlsx` -> itself; `output/books` (no/unknown suffix) ->
    books.xlsx + books.csv + books.json; an existing directory `output/` ->
    output/books.xlsx + .csv + .json."""
    paths: list[Path] = []
    for raw in outs:
        path = Path(raw).expanduser()
        if path.is_dir():
            path = path / "books"
        if path.suffix.lower() in WRITERS:
            paths.append(path)
        else:
            paths.extend(path.with_name(path.name + ext) for ext in DEFAULT_FORMATS)
    unique: list[Path] = []
    for p in paths:
        if p not in unique:
            unique.append(p)
    return unique


def export(
    books: list[Book],
    path: Path,
    meta: dict[str, object] | None = None,
    *,
    csv_delimiter: str = ",",
) -> Path:
    """Write `books` to `path`; the format is picked by the file extension.
    `meta` (run parameters) goes to the "About" sheet of the Excel report."""
    writer = WRITERS[path.suffix.lower()]
    path.parent.mkdir(parents=True, exist_ok=True)
    if writer is write_xlsx:
        return write_xlsx(books, path, meta=meta)
    if writer is write_csv:
        return write_csv(books, path, delimiter=csv_delimiter)
    return writer(books, path)


__all__ = ["COLUMNS", "Column", "DEFAULT_FORMATS", "WRITERS", "export", "resolve_outputs",
           "write_csv", "write_json", "write_xlsx"]
