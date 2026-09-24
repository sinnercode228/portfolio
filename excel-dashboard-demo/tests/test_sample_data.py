import csv
from datetime import date, timedelta

from xldash.sample_data import (HALT_REASONS, MACHINES, MESSY_DUPLICATES, MESSY_INVALID_ROWS,
                                SHIFT_HOURS, generate_production_rows, generate_worklog_rows,
                                write_production_csv)


def test_generator_is_deterministic():
    assert generate_production_rows(seed=5) == generate_production_rows(seed=5)
    assert generate_production_rows(seed=5) != generate_production_rows(seed=6)


def test_generator_covers_30_days_and_all_dimensions():
    rows = generate_production_rows(start=date(2026, 9, 1), days=30)
    dates = {r["date"] for r in rows}
    assert min(dates) >= date(2026, 9, 1) and max(dates) <= date(2026, 9, 30)
    assert all(d.weekday() != 6 for d in dates)                  # Sundays off
    assert len(dates) >= 25
    assert {r["machine"] for r in rows} == {m[0] for m in MACHINES}
    assert {r["shift"] for r in rows} == {"Day", "Evening", "Night"}
    assert len({r["department"] for r in rows}) == 4
    assert len({r["employee"] for r in rows}) >= 15


def test_generator_values_are_consistent():
    reasons = {v[0] for v in HALT_REASONS.values()}
    for r in generate_production_rows():
        assert 0 <= r["halt_minutes"] < SHIFT_HOURS * 60
        assert abs(r["run_hours"] + r["halt_minutes"] / 60 - SHIFT_HOURS) < 0.01
        assert (r["halt_minutes"] > 0) == (r["halt_reason"] != "")
        assert r["halt_reason"] in reasons | {""}


def test_one_row_per_machine_shift_day():
    rows = generate_production_rows()
    keys = [(r["date"], r["shift"], r["machine"]) for r in rows]
    assert len(keys) == len(set(keys))
    # an operator never works two machines in the same shift
    ops = [(r["date"], r["shift"], r["employee"]) for r in rows]
    assert len(ops) == len(set(ops))


def test_messy_csv_adds_duplicates_and_invalid_rows(tmp_path):
    clean = tmp_path / "clean.csv"
    messy = tmp_path / "messy.csv"
    n_clean = write_production_csv(clean, messy=False)
    n_messy = write_production_csv(messy, messy=True)
    assert n_messy == n_clean + MESSY_DUPLICATES + MESSY_INVALID_ROWS


def test_ru_csv_uses_semicolon_and_decimal_comma(tmp_path):
    path = tmp_path / "ru.csv"
    write_production_csv(path, lang="ru")
    with path.open(encoding="utf-8-sig") as fh:
        rows = list(csv.reader(fh, delimiter=";"))
    assert rows[0][0] == "Дата"
    assert rows[1][0].count(".") == 2                              # dd.mm.yyyy
    assert any("," in r[5] for r in rows[1:])                      # 7,25


def test_worklog_spans_outside_the_invoice_month():
    rows = generate_worklog_rows()
    dates = [r["date"] for r in rows]
    assert min(dates) < date(2026, 9, 1) and max(dates) > date(2026, 9, 30)
    per_day = {}
    for r in rows:
        per_day[(r["date"], r["employee"])] = per_day.get((r["date"], r["employee"]), 0) + r["hours"]
        assert 0 < r["hours"] <= 8.5
        assert r["billable"] in ("Yes", "No")
    assert max(per_day.values()) <= 8.5 + 1e-9
    assert all(d.weekday() < 5 for d in dates)
    assert timedelta(days=30) < max(dates) - min(dates)
