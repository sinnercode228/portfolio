#!/usr/bin/env python3
"""Generate fictional sample CSV files (production log, work log, rates).

Examples:
    python generate_sample_data.py                      # EN + RU samples into data/
    python generate_sample_data.py --days 60 --seed 1   # longer period, other random data
    python generate_sample_data.py --clean              # no intentional noise in the log
"""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from xldash.sample_data import write_production_csv, write_rates_csv, write_worklog_csv


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out-dir", default="data", help="folder for the CSV files (default: data)")
    p.add_argument("--start", default="2026-09-01", help="first day, YYYY-MM-DD (default 2026-09-01)")
    p.add_argument("--days", type=int, default=30, help="number of days (default 30)")
    p.add_argument("--seed", type=int, default=42, help="random seed (default 42)")
    p.add_argument("--lang", choices=["en", "ru", "both"], default="both")
    p.add_argument("--clean", action="store_true", help="do not add realistic export noise")
    args = p.parse_args(argv)

    out = Path(args.out_dir)
    start = date.fromisoformat(args.start)
    langs = ["en", "ru"] if args.lang == "both" else [args.lang]
    for lang in langs:
        suffix = "" if lang == "en" else "_ru"
        n = write_production_csv(out / f"production_log_sample{suffix}.csv", start, args.days,
                                 args.seed, lang, messy=not args.clean)
        w = write_worklog_csv(out / f"work_log_sample{suffix}.csv", seed=args.seed + 7, lang=lang)
        r = write_rates_csv(out / f"rates_sample{suffix}.csv", lang=lang)
        print(f"[{lang}] production_log_sample{suffix}.csv: {n} rows | "
              f"work_log_sample{suffix}.csv: {w} rows | rates_sample{suffix}.csv: {r} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
