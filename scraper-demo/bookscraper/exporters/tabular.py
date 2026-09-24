"""Column layout shared by all exporters + CSV / JSON writers."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path

from bookscraper.models import Book


@dataclass(frozen=True)
class Column:
    key: str          # Book attribute
    header: str       # human-readable header (xlsx / csv / sheets)
    width: int        # Excel column width (characters)
    number_format: str | None = None
    hyperlink: bool = False


COLUMNS: tuple[Column, ...] = (
    Column("title", "Title", 45),
    Column("category", "Category", 18),
    Column("price", "Price", 10, '"£"#,##0.00'),
    Column("availability", "In stock (qty)", 14, "0"),
    Column("rating", "Rating (1-5)", 12, "0"),
    Column("upc", "UPC", 19),
    Column("num_reviews", "Reviews", 9, "0"),
    Column("product_url", "Product URL", 16, hyperlink=True),
    Column("image_url", "Image URL", 16, hyperlink=True),
    Column("description", "Description", 80),
    Column("scraped_at", "Scraped at (UTC)", 22),
)


def row_values(book: Book) -> list[object]:
    return [getattr(book, col.key) for col in COLUMNS]


def _csv_cell(value: object, decimal_comma: bool) -> object:
    if value is None:
        return ""
    if decimal_comma and isinstance(value, float):
        return str(value).replace(".", ",")
    return value


def write_csv(books: list[Book], path: Path, *, delimiter: str = ",") -> Path:
    """utf-8-sig: the BOM makes Excel open the file with the right encoding.
    delimiter=";" is what Excel with a Russian/European locale expects; that
    locale also uses a decimal comma, so prices are written as 51,77 then."""
    decimal_comma = delimiter == ";"
    with path.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh, delimiter=delimiter)
        writer.writerow([c.header for c in COLUMNS])
        for book in books:
            writer.writerow([_csv_cell(v, decimal_comma) for v in row_values(book)])
    return path


def write_json(books: list[Book], path: Path) -> Path:
    path.write_text(
        json.dumps([b.to_dict() for b in books], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path
