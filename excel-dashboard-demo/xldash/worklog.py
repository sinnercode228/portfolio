"""Time log + rates loading and the reference maths for the invoice/payroll workbook."""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path

from .csvio import (Issue, LoadReport, canonical_spelling, clean_text, map_headers, parse_date,
                    parse_number, read_text, sniff_rows)

LOG_ALIASES = {
    "date": ("дата", "day"),
    "employee": ("сотрудник", "исполнитель", "specialist", "name", "фио"),
    "project": ("проект", "client project"),
    "task": ("задача", "description", "описание", "работа"),
    "hours": ("часы", "hrs", "duration h", "время ч", "duration"),
    "billable": ("оплачиваемо", "billable?", "к оплате", "биллинг"),
}
RATE_ALIASES = {
    "employee": ("сотрудник", "исполнитель", "name"),
    "role": ("роль", "должность", "position"),
    "bill_rate": ("ставка клиенту", "bill rate", "rate", "ставка"),
    "pay_rate": ("ставка сотруднику", "pay rate", "cost rate", "себестоимость"),
}
YES = {"yes", "y", "true", "1", "да", "д", "+", "billable"}
NO = {"no", "n", "false", "0", "нет", "н", "-", "non-billable"}


@dataclass(frozen=True)
class WorkEntry:
    date: date
    employee: str
    project: str
    task: str
    hours: float
    billable: bool


@dataclass(frozen=True)
class Rate:
    employee: str
    role: str
    bill_rate: float
    pay_rate: float


def load_worklog_csv(path: str | Path) -> tuple[list[WorkEntry], LoadReport]:
    rows = sniff_rows(read_text(path))
    if not rows:
        raise ValueError(f"{path}: file is empty")
    cols = map_headers(rows[0], LOG_ALIASES)
    missing = [k for k in ("date", "employee", "hours") if k not in cols]
    if missing:
        raise ValueError(f"{path}: missing required column(s): {', '.join(missing)}")
    report = LoadReport()
    parsed = []
    for line_no, raw in enumerate(rows[1:], start=2):
        if not any(c.strip() for c in raw):
            continue
        report.total_lines += 1
        get = lambda k: raw[cols[k]] if k in cols and cols[k] < len(raw) else ""  # noqa: E731
        try:
            d = parse_date(get("date"))
            hours = parse_number(get("hours"))
        except ValueError as exc:
            report.issues.append(Issue(line_no, "rejected_unreadable", str(exc)))
            continue
        if not 0 < hours <= 24:
            report.issues.append(Issue(line_no, "rejected_hours", f"hours={hours}"))
            continue
        employee = clean_text(get("employee"))
        if not employee:
            report.issues.append(Issue(line_no, "rejected_no_employee", "employee is empty"))
            continue
        flag = clean_text(get("billable")).casefold()
        if flag in YES:
            billable = True
        elif flag in NO:
            billable = False
        else:
            billable = True
            report.issues.append(Issue(line_no, "assumed_billable", f"billable={flag!r} -> yes"))
        parsed.append({"date": d, "employee": employee, "project": clean_text(get("project")) or "-",
                       "task": clean_text(get("task")), "hours": round(hours, 4),
                       "billable": billable})
    for key in ("employee", "project"):
        mapping = canonical_spelling([p[key] for p in parsed])
        for p in parsed:
            p[key] = mapping[p[key]]
    entries = sorted((WorkEntry(**p) for p in parsed), key=lambda e: (e.date, e.employee))
    report.accepted = len(entries)
    return entries, report


def load_rates_csv(path: str | Path) -> list[Rate]:
    rows = sniff_rows(read_text(path))
    if not rows:
        raise ValueError(f"{path}: file is empty")
    cols = map_headers(rows[0], RATE_ALIASES)
    missing = [k for k in RATE_ALIASES if k not in cols]
    if missing:
        raise ValueError(f"{path}: missing required column(s): {', '.join(missing)}")
    rates = []
    for line_no, raw in enumerate(rows[1:], start=2):
        if not any(c.strip() for c in raw):
            continue
        get = lambda k: raw[cols[k]] if cols[k] < len(raw) else ""  # noqa: E731
        employee = clean_text(get("employee"))
        if not employee:
            raise ValueError(f"{path}, line {line_no}: employee is empty")
        try:
            bill, pay = parse_number(get("bill_rate")), parse_number(get("pay_rate"))
        except ValueError as exc:
            raise ValueError(f"{path}, line {line_no}: bad rate for {employee}: {exc}") from None
        if bill < 0 or pay < 0:
            raise ValueError(f"{path}, line {line_no}: negative rate for {employee}")
        rates.append(Rate(employee, clean_text(get("role")), bill, pay))
    if not rates:
        raise ValueError(f"{path}: no rates found")
    names = [r.employee.casefold() for r in rates]
    dupes = {n for n in names if names.count(n) > 1}
    if dupes:
        raise ValueError(f"{path}: duplicate employees in rates: {', '.join(sorted(dupes))}")
    return rates


def match_rate_names(entries: list[WorkEntry], rates: list[Rate]) -> list[WorkEntry]:
    """Use the rates table's spelling for names that differ only in case / spaces.
    Excel's MATCH and SUMIFS ignore case anyway; this keeps the workbook, the
    warnings and the Python reference consistent."""
    by_key = {r.employee.casefold(): r.employee for r in rates}
    return [replace(e, employee=by_key.get(e.employee.casefold(), e.employee)) for e in entries]


# ----------------------------------------------------------------- reference maths

def billed_hours(hours: float, increment: float) -> float:
    """ROUNDUP(hours / increment, 0) * increment - each entry is rounded up separately."""
    if increment <= 0:
        return hours
    return math.ceil(round(hours / increment, 9)) * increment


def invoice_reference(entries, rates, date_from: date, date_to: date, increment: float,
                      tax_rate: float = 0.0) -> dict:
    rate_by = {r.employee: r for r in rates}
    per_emp = defaultdict(lambda: {"worked": 0.0, "billable_actual": 0.0, "billed_hours": 0.0,
                                   "amount": 0.0, "cost": 0.0})
    per_project = defaultdict(lambda: {"billed_hours": 0.0, "amount": 0.0})
    for e in entries:
        if not date_from <= e.date <= date_to:
            continue
        rate = rate_by.get(e.employee)
        bill, pay = (rate.bill_rate, rate.pay_rate) if rate else (0.0, 0.0)
        g = per_emp[e.employee]
        g["worked"] += e.hours
        g["cost"] += round(e.hours * pay, 2)
        if e.billable:
            bh = billed_hours(e.hours, increment)
            g["billable_actual"] += e.hours
            g["billed_hours"] += bh
            g["amount"] += round(bh * bill, 2)
            per_project[e.project]["billed_hours"] += bh
            per_project[e.project]["amount"] += round(bh * bill, 2)
    lines = {}
    for r in rates:
        g = per_emp.get(r.employee, {"billed_hours": 0.0})
        lines[r.employee] = round(g["billed_hours"] * r.bill_rate, 2)
    subtotal = round(sum(lines.values()), 2)
    tax = round(subtotal * tax_rate, 2)
    return {"per_employee": dict(per_emp), "per_project": dict(per_project), "lines": lines,
            "subtotal": subtotal, "tax": tax, "total": round(subtotal + tax, 2),
            "unknown_employees": sorted({e.employee for e in entries if e.employee not in rate_by})}
