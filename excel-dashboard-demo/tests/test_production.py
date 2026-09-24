from datetime import date

import pytest

from xldash.production import (UNSPECIFIED, dimension_values, filter_records, load_production_csv,
                               summarize)
from xldash.sample_data import write_production_csv


@pytest.mark.parametrize("lang", ["en", "ru"])
def test_cleaning_recovers_the_clean_data(tmp_path, lang):
    """Messy export -> loader -> identical to the clean export (except blank reasons)."""
    write_production_csv(tmp_path / "clean.csv", lang=lang, messy=False)
    write_production_csv(tmp_path / "messy.csv", lang=lang, messy=True)
    clean, clean_report = load_production_csv(tmp_path / "clean.csv", lang=lang)
    messy, report = load_production_csv(tmp_path / "messy.csv", lang=lang)

    assert clean_report.issues == []
    assert report.count("dropped_duplicate") == 3
    assert report.rejected == 2
    assert len(messy) == len(clean)
    for a, b in zip(clean, messy):
        if b.halt_reason == UNSPECIFIED[lang]:
            assert a.halt_minutes > 0
            a = a.__class__(**{**a.__dict__, "halt_reason": UNSPECIFIED[lang]})
        assert a == b


def test_rejects_and_reports_bad_rows(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text(
        "date,shift,department,machine,employee,run_hours,halt_minutes,halt_reason\n"
        "2026-09-01,Day,Welding,WLD-01,A,8,0,\n"
        "2026-09-01,Day,Welding,WLD-02,B,7,60,\n"            # halt without reason
        "not a date,Day,Welding,WLD-01,A,8,0,\n"
        "2026-09-02,Day,Welding,WLD-01,A,-1,0,\n"
        "2026-09-02,Day,Welding,WLD-01,A,20,600,Breakdown\n"  # 30 h in one row
        "2026-09-02,Day,Welding,,A,8,0,\n"
        "2026-09-03,Day,Welding,WLD-01,A,x,0,\n",
        encoding="utf-8")
    records, report = load_production_csv(path)
    assert len(records) == 2
    assert records[1].halt_reason == "Unspecified"
    kinds = sorted(i.kind for i in report.issues)
    assert kinds == ["filled_blank_reason", "rejected_bad_date", "rejected_bad_number",
                     "rejected_negative", "rejected_no_machine", "rejected_over_24h"]
    assert "2 of 7 rows accepted" in report.summary()


def test_missing_column_is_a_clear_error(tmp_path):
    path = tmp_path / "x.csv"
    path.write_text("date,shift,machine\n2026-09-01,Day,A\n", encoding="utf-8")
    with pytest.raises(ValueError, match="missing required column"):
        load_production_csv(path)


def test_cp1251_file_is_readable(tmp_path):
    path = tmp_path / "win.csv"
    path.write_bytes(("Дата;Смена;Цех;Станок;ФИО;Часы работы;Простой;Причина\n"
                      "01.09.2026;Дневная;Сварка;WLD-01;Иванов И.И.;7,5;30;Поломка\n").encode("cp1251"))
    records, _ = load_production_csv(path, lang="ru")
    assert records[0].employee == "Иванов И.И." and records[0].run_hours == 7.5
    assert records[0].halt_minutes == 30 and records[0].date == date(2026, 9, 1)


def test_summary_and_filters(production):
    records, _, _ = production
    all_ = summarize(records)
    assert all_["rows"] == len(records)
    assert all_["run_hours"] == pytest.approx(sum(r.run_hours for r in records))
    assert sum(g["run"] for g in all_["by_machine"].values()) == pytest.approx(all_["run_hours"])
    assert sum(g["halt"] for g in all_["by_reason"].values()) == pytest.approx(all_["halt_hours"])
    assert 0.75 < all_["availability"] < 0.95

    shift = dimension_values(records)["shift"][0]
    one_shift = summarize(records, shift=shift)
    assert 0 < one_shift["rows"] < all_["rows"]
    assert all(r.shift == shift for r in filter_records(records, shift=shift.upper()))  # case-insensitive
    week = summarize(records, date_from=date(2026, 9, 7), date_to=date(2026, 9, 13))
    assert week["rows"] < all_["rows"]
    assert summarize(records, date_from=date(2026, 9, 10), date_to=date(2026, 9, 9))["rows"] == 0


def test_dimension_values_order(production, lang):
    records, _, _ = production
    dims = dimension_values(records)
    expected = ["Day", "Evening", "Night"] if lang == "en" else ["Дневная", "Вечерняя", "Ночная"]
    assert dims["shift"] == expected
    assert dims["machine"] == sorted(dims["machine"], key=str.casefold)
