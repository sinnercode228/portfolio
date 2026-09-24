#!/usr/bin/env python3
"""Build a time-and-materials invoice + payroll workbook from a work log and a rates table.

Examples:
    python build_invoice.py data/work_log_sample.csv data/rates_sample.csv
    python build_invoice.py data/work_log_sample_ru.csv data/rates_sample_ru.csv --lang ru \\
        --currency RUB -o output/invoice_ru.xlsx
    python build_invoice.py log.csv rates.csv --from 2026-09-01 --to 2026-09-15 --increment 0.5 --tax 0.2
"""

from __future__ import annotations

import argparse
import calendar
import sys
from datetime import date

from xldash.invoice import build_invoice
from xldash.worklog import load_rates_csv, load_worklog_csv


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("worklog", help="CSV: date, employee, project, task, hours, billable")
    p.add_argument("rates", help="CSV: employee, role, bill_rate, pay_rate")
    p.add_argument("-o", "--output", default="output/invoice.xlsx")
    p.add_argument("--lang", choices=["en", "ru"], default="en")
    p.add_argument("--from", dest="date_from", help="period start YYYY-MM-DD "
                   "(default: first day of the month with the most log entries)")
    p.add_argument("--to", dest="date_to", help="period end YYYY-MM-DD (default: end of that month)")
    p.add_argument("--invoice-no", default=None, help="default: <year>-<month>-001")
    p.add_argument("--invoice-date", default=None, help="default: day after the period end")
    p.add_argument("--terms", type=int, default=14, help="payment terms in days (default 14)")
    p.add_argument("--increment", type=float, default=0.25, help="billing increment in hours (default 0.25)")
    p.add_argument("--tax", type=float, default=0.0, help="tax/VAT rate 0-1 (default 0)")
    p.add_argument("--currency", default=None, help="default: USD (en) / RUB (ru)")
    args = p.parse_args(argv)

    try:
        entries, report = load_worklog_csv(args.worklog)
        rates = load_rates_csv(args.rates)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if not entries:
        print("error: the work log has no valid rows", file=sys.stderr)
        return 2
    print(f"Loaded {args.worklog}: {report.summary()}; rates for {len(rates)} people")
    unknown = sorted({e.employee for e in entries} - {r.employee for r in rates})
    if unknown:
        print(f"warning: no rate for {', '.join(unknown)} (billed at 0)")

    if args.date_from:
        d_from = date.fromisoformat(args.date_from)
    else:
        months = {}
        for e in entries:
            months[(e.date.year, e.date.month)] = months.get((e.date.year, e.date.month), 0) + 1
        y, m = max(months, key=months.get)
        d_from = date(y, m, 1)
    d_to = date.fromisoformat(args.date_to) if args.date_to else \
        date(d_from.year, d_from.month, calendar.monthrange(d_from.year, d_from.month)[1])
    if d_to < d_from:
        p.error("--to is earlier than --from")
    out = build_invoice(
        entries, rates, args.output, lang=args.lang, period_from=d_from, period_to=d_to,
        invoice_no=args.invoice_no or f"{d_from:%Y-%m}-001",
        invoice_date=date.fromisoformat(args.invoice_date) if args.invoice_date else None,
        terms_days=args.terms, increment=args.increment, tax_rate=args.tax,
        currency=args.currency or ("RUB" if args.lang == "ru" else "USD"))
    print(f"Period {d_from} .. {d_to}. Saved {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
