"""Load and clean a production/operations log; reference aggregations.

The aggregations here mirror what the Excel formulas compute. They are used by
the tests to prove the workbook formulas return the same numbers as Python.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .csvio import (Issue, LoadReport, canonical_spelling, clean_text, map_headers,
                    parse_date, parse_number, read_text, sniff_rows)

ALIASES: dict[str, tuple[str, ...]] = {
    "date": ("дата", "day", "work date", "дата смены"),
    "shift": ("смена",),
    "department": ("цех", "участок", "отдел", "dept", "подразделение"),
    "machine": ("оборудование", "станок", "машина", "equipment", "machine id", "линия"),
    "employee": ("сотрудник", "оператор", "фио", "operator", "worker"),
    "run_hours": ("часы работы", "работа ч", "run h", "run hours", "runtime h", "hours run"),
    "halt_minutes": ("простой мин", "простой", "halt min", "downtime min", "downtime minutes",
                     "stop minutes"),
    "halt_reason": ("причина простоя", "причина", "reason", "downtime reason", "stop reason"),
}
REQUIRED = ("date", "shift", "department", "machine", "employee", "run_hours", "halt_minutes")

UNSPECIFIED = {"en": "Unspecified", "ru": "Не указана"}


@dataclass(frozen=True)
class ProdRecord:
    date: date
    shift: str
    department: str
    machine: str
    employee: str
    run_hours: float
    halt_minutes: float
    halt_reason: str

    @property
    def halt_hours(self) -> float:
        return self.halt_minutes / 60


def load_production_csv(path: str | Path, lang: str = "en") -> tuple[list[ProdRecord], LoadReport]:
    """Read a raw log, normalise it and report every fix / rejected line."""
    rows = sniff_rows(read_text(path))
    report = LoadReport()
    if not rows:
        raise ValueError(f"{path}: file is empty")
    cols = map_headers(rows[0], ALIASES)
    missing = [k for k in REQUIRED if k not in cols]
    if missing:
        raise ValueError(f"{path}: missing required column(s): {', '.join(missing)}; "
                         f"found header {rows[0]}")

    parsed: list[tuple[int, dict]] = []
    for line_no, raw in enumerate(rows[1:], start=2):
        if not any(c.strip() for c in raw):
            continue
        report.total_lines += 1
        get = lambda k: raw[cols[k]] if cols.get(k) is not None and cols[k] < len(raw) else ""  # noqa: E731
        try:
            d = parse_date(get("date"))
        except ValueError as exc:
            report.issues.append(Issue(line_no, "rejected_bad_date", str(exc)))
            continue
        try:
            run = parse_number(get("run_hours"))
            halt = parse_number(get("halt_minutes"))
        except ValueError as exc:
            report.issues.append(Issue(line_no, "rejected_bad_number", str(exc)))
            continue
        if run < 0 or halt < 0:
            report.issues.append(Issue(line_no, "rejected_negative", f"run={run}, halt={halt}"))
            continue
        if run + halt / 60 > 24.0001:
            report.issues.append(Issue(line_no, "rejected_over_24h", f"run={run}, halt={halt} min"))
            continue
        rec = {k: clean_text(get(k)) for k in ("shift", "department", "machine", "employee",
                                               "halt_reason")}
        if not rec["machine"]:
            report.issues.append(Issue(line_no, "rejected_no_machine", "machine is empty"))
            continue
        for k in ("shift", "department", "employee"):
            if not rec[k]:
                rec[k] = UNSPECIFIED[lang]
                report.issues.append(Issue(line_no, "filled_blank_" + k, UNSPECIFIED[lang]))
        if halt > 0 and not rec["halt_reason"]:
            rec["halt_reason"] = UNSPECIFIED[lang]
            report.issues.append(Issue(line_no, "filled_blank_reason", UNSPECIFIED[lang]))
        if halt == 0:
            rec["halt_reason"] = ""
        rec.update(date=d, run_hours=round(run, 4), halt_minutes=round(halt, 4))
        parsed.append((line_no, rec))

    # unify spelling variants ("day" / "Day", "cnc-02" / "CNC-02")
    for key in ("shift", "department", "machine", "employee", "halt_reason"):
        mapping = canonical_spelling([r[key] for _, r in parsed if r[key]])
        for line_no, r in parsed:
            if r[key] and mapping[r[key]] != r[key]:
                report.issues.append(Issue(line_no, "normalised_" + key,
                                           f"{r[key]!r} -> {mapping[r[key]]!r}"))
                r[key] = mapping[r[key]]

    records: list[ProdRecord] = []
    seen: set[ProdRecord] = set()
    for line_no, r in parsed:
        record = ProdRecord(**r)
        if record in seen:
            report.issues.append(Issue(line_no, "dropped_duplicate", "exact duplicate of an earlier row"))
            continue
        seen.add(record)
        records.append(record)
    records.sort(key=lambda x: (x.date, x.shift, x.machine))
    report.accepted = len(records)
    return records, report


# ----------------------------------------------------------------- reference maths

def filter_records(records, shift=None, department=None, date_from=None, date_to=None):
    """Same semantics as the workbook: None/'All' = no filter, dates inclusive,
    text comparison case-insensitive (like SUMIFS)."""
    def ok(r: ProdRecord) -> bool:
        if shift and r.shift.casefold() != shift.casefold():
            return False
        if department and r.department.casefold() != department.casefold():
            return False
        if date_from and r.date < date_from:
            return False
        if date_to and r.date > date_to:
            return False
        return True
    return [r for r in records if ok(r)]


def _avail(run: float, halt_h: float) -> float | None:
    return run / (run + halt_h) if run + halt_h else None


def summarize(records, **filters) -> dict:
    rows = filter_records(records, **filters)
    total_run = sum(r.run_hours for r in rows)
    total_halt = sum(r.halt_hours for r in rows)

    def group(key):
        acc = defaultdict(lambda: {"run": 0.0, "halt": 0.0, "shifts": 0, "events": 0})
        for r in rows:
            g = acc[getattr(r, key)]
            g["run"] += r.run_hours
            g["halt"] += r.halt_hours
            g["shifts"] += 1
            g["events"] += 1 if r.halt_minutes > 0 else 0
        for g in acc.values():
            g["availability"] = _avail(g["run"], g["halt"])
        return dict(acc)

    reasons = defaultdict(lambda: {"halt": 0.0, "events": 0})
    matrix = defaultdict(float)
    for r in rows:
        if r.halt_minutes > 0:
            reasons[r.halt_reason]["halt"] += r.halt_hours
            reasons[r.halt_reason]["events"] += 1
            matrix[(r.machine, r.halt_reason)] += r.halt_hours

    return {
        "rows": len(rows),
        "run_hours": total_run,
        "halt_hours": total_halt,
        "availability": _avail(total_run, total_halt),
        "halt_events": sum(1 for r in rows if r.halt_minutes > 0),
        "by_machine": group("machine"),
        "by_employee": group("employee"),
        "by_department": group("department"),
        "by_reason": dict(reasons),
        "machine_reason": dict(matrix),
    }


def dimension_values(records) -> dict[str, list[str]]:
    """Distinct values used to build the summary tables and dropdowns."""
    order = {"shift": [], "department": [], "machine": [], "employee": [], "halt_reason": []}
    seen = {k: set() for k in order}
    for r in sorted(records, key=lambda x: (x.date,)):
        for k in order:
            v = getattr(r, k)
            if v and v not in seen[k]:
                seen[k].add(v)
                order[k].append(v)
    order["shift"].sort(key=_shift_rank)
    for k in ("department", "machine", "employee", "halt_reason"):
        order[k].sort(key=str.casefold)
    return order


_SHIFT_ORDER = ("morning", "утро", "утренняя", "day", "дневная", "день", "1",
                "afternoon", "evening", "вечерняя", "вечер", "2", "night", "ночная", "ночь", "3")


def _shift_rank(name: str) -> tuple[int, str]:
    """Day -> Evening -> Night (in either language); unknown names go last, A-Z."""
    key = name.casefold().replace("shift", "").replace("смена", "").strip()
    return (_SHIFT_ORDER.index(key) if key in _SHIFT_ORDER else len(_SHIFT_ORDER), key)


def machine_department(records) -> dict[str, str]:
    """Most frequent department per machine (a machine can be moved between shops)."""
    counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for r in records:
        counts[r.machine][r.department] += 1
    return {m: max(d.items(), key=lambda kv: kv[1])[0] for m, d in counts.items()}
