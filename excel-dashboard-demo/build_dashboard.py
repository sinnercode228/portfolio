#!/usr/bin/env python3
"""Turn a raw production log (CSV) into the Excel dashboard workbook.

Examples:
    python build_dashboard.py data/production_log_sample.csv
    python build_dashboard.py data/production_log_sample_ru.csv --lang ru -o output/dashboard_ru.xlsx
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from xldash.dashboard import build_dashboard
from xldash.formula_check import add_preview_values
from xldash.production import load_production_csv


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("csv", help="production log: date, shift, department, machine, employee, "
                               "run hours, halt minutes, halt reason (EN or RU headers)")
    p.add_argument("-o", "--output", default="output/dashboard.xlsx")
    p.add_argument("--lang", choices=["en", "ru"], default="en", help="workbook language")
    p.add_argument("--target", type=float, default=0.85, help="availability target, 0-1 (default 0.85)")
    p.add_argument("--no-preview-values", action="store_true",
                   help="do not store computed values next to the formulas "
                        "(faster; previews without Excel then show 0)")
    args = p.parse_args(argv)
    if not 0 <= args.target <= 1:
        p.error("--target must be between 0 and 1")

    try:
        records, report = load_production_csv(args.csv, lang=args.lang)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"Loaded {args.csv}: {report.summary()}")
    for issue in report.issues:
        if issue.kind.startswith("rejected"):
            print(f"  {issue}")
    if not records:
        print("error: no valid rows", file=sys.stderr)
        return 2
    try:
        out = build_dashboard(records, Path(args.output), lang=args.lang, report=report,
                              target=args.target)
    except OSError as exc:
        hint = " (is it open in Excel? close it and run again)" if isinstance(exc, PermissionError) else ""
        print(f"error: cannot write {args.output}: {exc.strerror or exc}{hint}", file=sys.stderr)
        return 2
    print(f"Saved {out}")
    if not args.no_preview_values:
        print(add_preview_values(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
