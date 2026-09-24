"""Tolerant CSV reading shared by the loaders.

Real exports differ in encoding (UTF-8 with/without BOM, Windows-1251),
delimiter (`,` `;` tab), decimal separator and date notation. These helpers
normalise all of that and keep track of problems per line.
"""

from __future__ import annotations

import csv
import io
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

DATE_FORMATS = ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%Y/%m/%d", "%d.%m.%y", "%Y-%m-%d %H:%M:%S")


@dataclass
class Issue:
    line: int          # 1-based line number in the file (header = 1)
    kind: str          # machine-readable code
    detail: str        # human-readable text

    def __str__(self) -> str:
        return f"line {self.line}: {self.kind} - {self.detail}"


@dataclass
class LoadReport:
    total_lines: int = 0
    accepted: int = 0
    issues: list[Issue] = field(default_factory=list)

    def count(self, kind: str) -> int:
        return sum(1 for i in self.issues if i.kind == kind)

    @property
    def rejected(self) -> int:
        return sum(1 for i in self.issues if i.kind.startswith("rejected"))

    def summary(self) -> str:
        kinds = Counter(i.kind for i in self.issues)
        parts = [f"{self.accepted} of {self.total_lines} rows accepted"]
        parts += [f"{k}: {v}" for k, v in sorted(kinds.items())]
        return "; ".join(parts)


def read_text(path: str | Path) -> str:
    raw = Path(path).read_bytes()
    for enc in ("utf-8-sig", "cp1251"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1")


def sniff_rows(text: str) -> list[list[str]]:
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        delimiter = dialect.delimiter
    except csv.Error:
        first = sample.splitlines()[0] if sample else ""
        delimiter = max(",;\t", key=first.count)
    return list(csv.reader(io.StringIO(text), delimiter=delimiter))


def norm_header(name: str) -> str:
    return re.sub(r"[\s_,.()]+", " ", name.strip().lower().replace("ё", "е")).strip()


def map_headers(header: list[str], aliases: dict[str, tuple[str, ...]]) -> dict[str, int]:
    """Return {canonical_key: column_index}. Raises ValueError listing missing columns."""
    lookup = {}
    for key, names in aliases.items():
        for n in (key, *names):
            lookup[norm_header(n)] = key
    found: dict[str, int] = {}
    for idx, col in enumerate(header):
        key = lookup.get(norm_header(col))
        if key and key not in found:
            found[key] = idx
    return found


def parse_number(value: str) -> float:
    text = value.strip().replace(" ", "").replace(" ", "")
    if not text:
        raise ValueError("empty number")
    if "," in text and "." in text:          # 1,234.5 or 1.234,5
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    else:
        text = text.replace(",", ".")
    return float(text)


def parse_date(value: str) -> date:
    text = value.strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"unrecognised date {value!r}")


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def canonical_spelling(values: list[str]) -> dict[str, str]:
    """Map case-insensitive variants to the most frequent spelling
    ('day', 'DAY ' and 'Day' -> 'Day')."""
    by_key: dict[str, Counter] = {}
    for v in values:
        by_key.setdefault(v.casefold(), Counter())[v] += 1
    out = {}
    for variants in by_key.values():
        # most common; on a tie prefer the one with more capitals (looks "official")
        best = max(variants.items(), key=lambda kv: (kv[1], sum(c.isupper() for c in kv[0])))[0]
        for v in variants:
            out[v] = best
    return out
